from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Type, cast

import attrs
from andi.typeutils import is_typing_annotated, strip_annotated
from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy_poet import InjectionMiddleware, PageObjectInputProvider
from web_poet import (
    AnyResponse,
    BrowserHtml,
    BrowserResponse,
    HttpResponse,
    HttpResponseHeaders,
)
from web_poet.annotated import AnnotatedInstance
from web_poet.fields import get_fields_dict
from web_poet.utils import get_fq_class_name
from zyte_common_items import (
    Article,
    ArticleList,
    ArticleNavigation,
    AutoArticleListPage,
    AutoArticleNavigationPage,
    AutoArticlePage,
    AutoJobPostingPage,
    AutoProductListPage,
    AutoProductNavigationPage,
    AutoProductPage,
    Item,
    JobPosting,
    Product,
    ProductList,
    ProductNavigation,
)

from scrapy_zyte_api import Actions, ExtractFrom, Geolocation, Screenshot
from scrapy_zyte_api._annotations import _ActionResult
from scrapy_zyte_api.responses import ZyteAPITextResponse

try:
    # requires Scrapy >= 2.8
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = None


_ITEM_KEYWORDS: Dict[type, str] = {
    Product: "product",
    ProductList: "productList",
    ProductNavigation: "productNavigation",
    Article: "article",
    ArticleList: "articleList",
    ArticleNavigation: "articleNavigation",
    JobPosting: "jobPosting",
}
_AUTO_PAGES: Set[type] = {
    AutoArticlePage,
    AutoArticleListPage,
    AutoArticleNavigationPage,
    AutoJobPostingPage,
    AutoProductPage,
    AutoProductListPage,
    AutoProductNavigationPage,
}


# https://stackoverflow.com/a/25959545
def _field_cls(page_cls, field_name):
    for cls in page_cls.__mro__:
        if field_name in cls.__dict__:
            return cls
    # Only used with fields known to exist
    assert False  # noqa: B011


class ZyteApiProvider(PageObjectInputProvider):
    name = "zyte_api"

    provided_classes = {
        Actions,
        AnyResponse,
        Article,
        ArticleList,
        ArticleNavigation,
        BrowserHtml,
        BrowserResponse,
        Geolocation,
        JobPosting,
        Product,
        ProductList,
        ProductNavigation,
        Screenshot,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._injection_mw = None
        self._should_track_auto_fields = None
        self._tracked_auto_fields = set()

    def is_provided(self, type_: Callable) -> bool:
        return super().is_provided(strip_annotated(type_))

    def _track_auto_fields(self, crawler: Crawler, request: Request, cls: Type):
        if cls not in _ITEM_KEYWORDS:
            return
        if self._should_track_auto_fields is None:
            self._should_track_auto_fields = crawler.settings.getbool(
                "ZYTE_API_AUTO_FIELD_STATS", False
            )
        if self._should_track_auto_fields is False:
            return
        if self._injection_mw is None:
            try:
                self._injection_mw = crawler.get_downloader_middleware(
                    InjectionMiddleware
                )
            except AttributeError:
                for component in crawler.engine.downloader.middleware.middlewares:
                    if isinstance(component, InjectionMiddleware):
                        self._injection_mw = component
                        break
            if self._injection_mw is None:
                raise RuntimeError(
                    "Could not find the InjectionMiddleware among enabled "
                    "downloader middlewares. Please, ensure you have properly "
                    "configured scrapy-poet."
                )
        cls = self._injection_mw.registry.page_cls_for_item(request.url, cls) or cls
        if cls in self._tracked_auto_fields:
            return
        self._tracked_auto_fields.add(cls)
        if cls in _ITEM_KEYWORDS:
            auto_fields = set(attrs.fields_dict(cls))
        else:
            auto_cls = None
            for ancestor in cls.__mro__:
                if ancestor in _AUTO_PAGES:
                    auto_cls = ancestor
                    break
            auto_fields = set()
            if auto_cls:
                for field_name in get_fields_dict(cls):
                    field_cls = _field_cls(cls, field_name)
                    if field_cls is auto_cls:
                        auto_fields.add(field_name)
        cls_fqn = get_fq_class_name(cls)
        field_list = " ".join(sorted(auto_fields))
        crawler.stats.set_value(f"scrapy-zyte-api/auto_fields/{cls_fqn}", field_list)

    async def __call__(  # noqa: C901
        self, to_provide: Set[Callable], request: Request, crawler: Crawler
    ) -> Sequence[Any]:
        """Makes a Zyte API request to provide BrowserResponse and/or item dependencies."""
        results: List[Any] = []

        http_response = None
        screenshot_requested = Screenshot in to_provide
        for cls in list(to_provide):
            self._track_auto_fields(crawler, request, cast(type, cls))
            item = self.injector.weak_cache.get(request, {}).get(cls)
            if item:
                results.append(item)
                to_provide.remove(cls)

            # BrowserResponse takes precedence over HttpResponse
            elif (
                cls == AnyResponse
                and BrowserResponse not in to_provide
                and not screenshot_requested
            ):
                http_response = self.injector.weak_cache.get(request, {}).get(
                    HttpResponse
                )
                if http_response:
                    any_response = AnyResponse(response=http_response)
                    results.append(any_response)
                    to_provide.remove(cls)

        if not to_provide:
            return results

        html_requested = BrowserResponse in to_provide or BrowserHtml in to_provide

        zyte_api_meta = {
            **crawler.settings.getdict("ZYTE_API_PROVIDER_PARAMS"),
            **request.meta.get("zyte_api_provider", {}),
        }

        to_provide_stripped: Set[type] = set()
        extract_from_seen: Dict[str, str] = {}
        item_requested: bool = False

        for cls in to_provide:
            cls_stripped = strip_annotated(cls)
            assert isinstance(cls_stripped, type)
            if cls_stripped is Geolocation:
                if not is_typing_annotated(cls):
                    raise ValueError("Geolocation dependencies must be annotated.")
                zyte_api_meta["geolocation"] = cls.__metadata__[0]  # type: ignore[attr-defined]
                continue
            if cls_stripped is Actions:
                if not is_typing_annotated(cls):
                    raise ValueError(
                        "Actions dependencies must be annotated, "
                        "e.g. Annotated[Actions, actions([...list of actions...])]."
                    )
                zyte_api_meta["actions"] = []
                for action in cls.__metadata__[0]:  # type: ignore[attr-defined]
                    zyte_api_meta["actions"].append(
                        {
                            k: (
                                dict(v)
                                if isinstance(v, frozenset)
                                else list(v) if isinstance(v, tuple) else v
                            )
                            for k, v in action
                        }
                    )
                continue
            kw = _ITEM_KEYWORDS.get(cls_stripped)
            if not kw:
                continue
            item_requested = True
            to_provide_stripped.add(cls_stripped)
            zyte_api_meta[kw] = True
            if not is_typing_annotated(cls):
                continue
            metadata = cls.__metadata__  # type: ignore[attr-defined]
            for extract_from in ExtractFrom:
                if extract_from in metadata:
                    prev_extract_from = extract_from_seen.get(kw)
                    if prev_extract_from and prev_extract_from != extract_from:
                        raise ValueError(
                            f"Multiple different extractFrom specified for {kw}"
                        )
                    extract_from_seen[kw] = extract_from
                    options = zyte_api_meta.setdefault(f"{kw}Options", {})
                    options.setdefault("extractFrom", extract_from.value)
                    break

        http_response_needed = (
            AnyResponse in to_provide
            and BrowserResponse not in to_provide
            and BrowserHtml not in to_provide
            and not screenshot_requested
            and not http_response
        )

        extract_from = None  # type: ignore[assignment]
        for item_type, kw in _ITEM_KEYWORDS.items():
            options_name = f"{kw}Options"
            if item_type not in to_provide_stripped and options_name in zyte_api_meta:
                del zyte_api_meta[options_name]
            elif zyte_api_meta.get(options_name, {}).get("extractFrom"):
                extract_from = zyte_api_meta[options_name]["extractFrom"]

        if AnyResponse in to_provide:
            if (
                (item_requested and extract_from != "httpResponseBody")
                or extract_from == "browserHtml"
                or zyte_api_meta.get("browserHtml", False) is True
            ):
                html_requested = True
            elif extract_from == "httpResponseBody" or http_response_needed:
                zyte_api_meta["httpResponseBody"] = True
                zyte_api_meta["httpResponseHeaders"] = True

        if html_requested:
            zyte_api_meta["browserHtml"] = True
        if screenshot_requested:
            zyte_api_meta["screenshot"] = True

        api_request = Request(
            url=request.url,
            meta={
                "zyte_api": zyte_api_meta,
                "zyte_api_default_params": False,
            },
            callback=NO_CALLBACK,
        )
        api_response: ZyteAPITextResponse = await maybe_deferred_to_future(
            crawler.engine.download(api_request)
        )

        assert api_response.raw_api_response
        if html_requested:
            html = BrowserHtml(api_response.raw_api_response["browserHtml"])
        else:
            html = None
        if BrowserHtml in to_provide:
            results.append(html)

        browser_response = None
        if BrowserResponse in to_provide:
            browser_response = BrowserResponse(
                url=api_response.url,
                status=api_response.status,
                html=html,
            )
            results.append(browser_response)

        if screenshot_requested:
            screenshot_b64 = api_response.raw_api_response["screenshot"]
            screenshot = Screenshot.from_base64(screenshot_b64)
            results.append(screenshot)

        if AnyResponse in to_provide:
            any_response = None  # type: ignore[assignment]

            if "browserHtml" in api_response.raw_api_response:
                any_response = AnyResponse(
                    response=browser_response
                    or BrowserResponse(
                        url=api_response.url,
                        status=api_response.status,
                        html=html,
                    )
                )
            elif (
                "httpResponseBody" in api_response.raw_api_response
                and "httpResponseHeaders" in api_response.raw_api_response
            ):
                any_response = AnyResponse(
                    response=HttpResponse(
                        url=api_response.url,
                        body=api_response.body,
                        status=api_response.status,
                        headers=HttpResponseHeaders.from_bytes_dict(
                            api_response.headers
                        ),
                    )
                )

            if any_response:
                results.append(any_response)

        for cls in to_provide:
            cls_stripped = strip_annotated(cls)
            assert isinstance(cls_stripped, type)
            if cls_stripped is Geolocation and is_typing_annotated(cls):
                result = AnnotatedInstance(Geolocation(), cls.__metadata__)  # type: ignore[attr-defined]
                results.append(result)
                continue
            if cls_stripped is Actions and is_typing_annotated(cls):
                actions_result: Optional[List[_ActionResult]]
                if "actions" in api_response.raw_api_response:
                    actions_result = [
                        _ActionResult(**action_result)
                        for action_result in api_response.raw_api_response["actions"]
                    ]
                else:
                    actions_result = None
                result = AnnotatedInstance(Actions(actions_result), cls.__metadata__)  # type: ignore[attr-defined]
                results.append(result)
                continue
            kw = _ITEM_KEYWORDS.get(cls_stripped)
            if not kw:
                continue
            assert issubclass(cls_stripped, Item)
            result = cls_stripped.from_dict(api_response.raw_api_response[kw])  # type: ignore[attr-defined]
            if is_typing_annotated(cls):
                result = AnnotatedInstance(result, cls.__metadata__)  # type: ignore[attr-defined]
            results.append(result)
        return results
