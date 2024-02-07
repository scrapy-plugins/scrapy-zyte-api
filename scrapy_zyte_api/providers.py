from typing import Any, Callable, Dict, List, Sequence, Set

from andi.typeutils import is_typing_annotated, strip_annotated
from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy_poet import AnnotatedResult, PageObjectInputProvider
from web_poet import (
    AnyResponse,
    BrowserHtml,
    BrowserResponse,
    HttpResponse,
    HttpResponseHeaders,
)
from zyte_common_items import (
    Article,
    ArticleList,
    ArticleNavigation,
    Item,
    JobPosting,
    Product,
    ProductList,
    ProductNavigation,
)

from scrapy_zyte_api._annotations import ExtractFrom, Geolocation
from scrapy_zyte_api.responses import ZyteAPITextResponse

try:
    # requires Scrapy >= 2.8
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = None


class ZyteApiProvider(PageObjectInputProvider):
    name = "zyte_api"

    provided_classes = {
        BrowserResponse,
        BrowserHtml,
        Product,
        ProductList,
        ProductNavigation,
        Article,
        ArticleList,
        ArticleNavigation,
        AnyResponse,
        JobPosting,
        Geolocation,
    }

    def is_provided(self, type_: Callable) -> bool:
        return super().is_provided(strip_annotated(type_))

    async def __call__(  # noqa: C901
        self, to_provide: Set[Callable], request: Request, crawler: Crawler
    ) -> Sequence[Any]:
        """Makes a Zyte API request to provide BrowserResponse and/or item dependencies."""
        results: List[Any] = []

        http_response = None
        for cls in list(to_provide):
            item = self.injector.weak_cache.get(request, {}).get(cls)
            if item:
                results.append(item)
                to_provide.remove(cls)

            # BrowserResponse takes precedence over HttpResponse
            elif cls == AnyResponse and BrowserResponse not in to_provide:
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
        item_keywords: Dict[type, str] = {
            Product: "product",
            ProductList: "productList",
            ProductNavigation: "productNavigation",
            Article: "article",
            ArticleList: "articleList",
            ArticleNavigation: "articleNavigation",
            JobPosting: "jobPosting",
        }

        zyte_api_meta = crawler.settings.getdict("ZYTE_API_PROVIDER_PARAMS")

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
            kw = item_keywords.get(cls_stripped)
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
                    # TODO better logic for overwriting the value
                    options["extractFrom"] = extract_from.value
                    break

        http_response_needed = (
            AnyResponse in to_provide
            and BrowserResponse not in to_provide
            and BrowserHtml not in to_provide
            and not http_response
        )

        extract_from = None  # type: ignore[assignment]
        for item_type, kw in item_keywords.items():
            options_name = f"{kw}Options"
            if item_type not in to_provide_stripped and options_name in zyte_api_meta:
                del zyte_api_meta[options_name]
            elif zyte_api_meta.get(options_name, {}).get("extractFrom"):
                extract_from = zyte_api_meta[options_name]["extractFrom"]

        if AnyResponse in to_provide:
            if (
                item_requested and extract_from != "httpResponseBody"
            ) or extract_from == "browserHtml":
                html_requested = True
            elif extract_from == "httpResponseBody" or http_response_needed:
                zyte_api_meta["httpResponseBody"] = True
                zyte_api_meta["httpResponseHeaders"] = True

        if html_requested:
            zyte_api_meta["browserHtml"] = True

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
                item = AnnotatedResult(Geolocation(), cls.__metadata__)  # type: ignore[attr-defined]
                results.append(item)
                continue
            kw = item_keywords.get(cls_stripped)
            if not kw:
                continue
            assert issubclass(cls_stripped, Item)
            item = cls_stripped.from_dict(api_response.raw_api_response[kw])  # type: ignore[attr-defined]
            if is_typing_annotated(cls):
                item = AnnotatedResult(item, cls.__metadata__)  # type: ignore[attr-defined]
            results.append(item)
        return results
