import json
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Mapping, Sequence
from logging import getLogger
from typing import TYPE_CHECKING, Any, Set, cast
from weakref import WeakKeyDictionary

from andi.typeutils import is_typing_annotated, strip_annotated
from scrapy import Request
from scrapy.crawler import Crawler
from scrapy_poet import PageObjectInputProvider
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
    AutoForumThreadPage,
    AutoJobPostingNavigationPage,
    AutoJobPostingPage,
    AutoProductListPage,
    AutoProductNavigationPage,
    AutoProductPage,
    AutoSerpPage,
    CustomAttributes,
    CustomAttributesMetadata,
    CustomAttributesValues,
    ForumThread,
    Item,
    JobPosting,
    JobPostingNavigation,
    Product,
    ProductList,
    ProductNavigation,
    Serp,
)
from zyte_common_items.fields import is_auto_field

from scrapy_zyte_api import Actions, ExtractFrom, Geolocation, Screenshot
from scrapy_zyte_api._annotations import _ActionResult, _from_hashable
from scrapy_zyte_api._page_inputs import CapturedResponse, NetworkCapture, ZyteApiParams
from scrapy_zyte_api._params import _FINGERPRINT_PARAM_KEYS
from scrapy_zyte_api.utils import _ENGINE_HAS_DOWNLOAD_ASYNC, maybe_deferred_to_future

logger = getLogger(__name__)

_PROVIDER_META_CACHE_MAX_SIZE = 1024
_provider_meta_caches: WeakKeyDictionary = WeakKeyDictionary()


def _get_provider_meta_cache(crawler) -> OrderedDict:
    try:
        return _provider_meta_caches[crawler]
    except KeyError:
        cache: OrderedDict = OrderedDict()
        _provider_meta_caches[crawler] = cache
        return cache


def _build_provider_meta_cache_key(
    to_provide,
    http_response_available: bool,
    provider_params: dict,
    meta_params: dict,
    for_fingerprint: bool,
) -> tuple:
    return (
        frozenset(to_provide),
        http_response_available,
        json.dumps(provider_params, sort_keys=True, separators=(",", ":")),
        # Only the keys matter: values, if any, are also in provider_params.
        tuple(sorted(meta_params)),
        # Parameters from dependencies are filtered when building parameters
        # for request fingerprinting, so cache entries can only be shared
        # between both scenarios if there are no such parameters.
        for_fingerprint
        and any(strip_annotated(cls) is ZyteApiParams for cls in to_provide),
    )


def _set_in_provider_meta_cache(
    cache: OrderedDict,
    key: tuple,
    meta: dict,
    html_requested: bool,
    max_size: int = _PROVIDER_META_CACHE_MAX_SIZE,
) -> None:
    if max_size <= 0:
        return
    cache[key] = (dict(meta), html_requested)
    while len(cache) > max_size:
        cache.popitem(last=False)


def _get_or_build_zyte_api_provider_meta(
    to_provide,
    request: Request,
    crawler: Crawler,
    *,
    provider_params,
    meta_params,
    screenshot_requested=None,
    http_response_available: bool = False,
    for_fingerprint: bool = False,
) -> tuple[dict, bool]:
    cache = _get_provider_meta_cache(crawler)
    key = _build_provider_meta_cache_key(
        to_provide,
        http_response_available,
        provider_params,
        meta_params,
        for_fingerprint,
    )
    try:
        meta, html_requested = cache[key]
        cache.move_to_end(key)
        return dict(meta), html_requested
    except KeyError:
        pass
    result = _build_zyte_api_provider_meta(
        to_provide,
        request,
        crawler,
        provider_params=provider_params,
        meta_params=meta_params,
        screenshot_requested=screenshot_requested,
        http_response_available=http_response_available,
        for_fingerprint=for_fingerprint,
    )
    _set_in_provider_meta_cache(cache, key, result[0], result[1])
    return result


if TYPE_CHECKING:
    from twisted.internet.defer import Deferred

    from scrapy_zyte_api.responses import ZyteAPITextResponse

try:
    # requires Scrapy >= 2.8
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = None  # type: ignore[assignment]


_ITEM_KEYWORDS: dict[type, str] = {
    Product: "product",
    ProductList: "productList",
    ProductNavigation: "productNavigation",
    Article: "article",
    ArticleList: "articleList",
    ArticleNavigation: "articleNavigation",
    ForumThread: "forumThread",
    JobPosting: "jobPosting",
    JobPostingNavigation: "jobPostingNavigation",
    Serp: "serp",
}
_AUTO_PAGES: set[type] = {
    AutoArticlePage,
    AutoArticleListPage,
    AutoArticleNavigationPage,
    AutoForumThreadPage,
    AutoJobPostingPage,
    AutoJobPostingNavigationPage,
    AutoProductPage,
    AutoProductListPage,
    AutoProductNavigationPage,
    AutoSerpPage,
}


# Zyte API parameters that have a dedicated input or annotation, and hence
# should not be set through ZyteApiParams.
_DEPENDENCY_MANAGED_PARAMS = frozenset(
    {
        "actions",
        "browserHtml",
        "customAttributes",
        "customAttributesOptions",
        "geolocation",
        "networkCapture",
        "screenshot",
        *_ITEM_KEYWORDS.values(),
    }
)
# Parameters from _DEPENDENCY_MANAGED_PARAMS already warned about, to warn only
# once per parameter.
_warned_dependency_managed_params: set[str] = set()


def _get_zyte_api_meta_params(request: Request) -> dict[str, Any]:
    request_params = request.meta.get("zyte_api_provider", {})
    if request_params is None:
        return {}
    if not isinstance(request_params, Mapping):
        raise ValueError(
            f"Request {request} has {request_params!r} as the "
            f"zyte_api_provider value, but only dictionaries are supported."
        )
    return dict(request_params)


def _get_zyte_api_provider_params(request: Request, crawler: Crawler) -> dict[str, Any]:
    setting_params = crawler.settings.getdict("ZYTE_API_PROVIDER_PARAMS")

    return {
        **setting_params,
        **_get_zyte_api_meta_params(request),
    }


def _get_zyte_api_dependency_params(to_provide: Set[Callable]) -> dict[str, Any]:
    """Return the Zyte API parameters requested through
    :class:`~scrapy_zyte_api.ZyteApiParams` dependencies."""
    params: dict[str, Any] = {}
    for cls in to_provide:
        if strip_annotated(cls) is not ZyteApiParams:
            continue
        if not is_typing_annotated(cls):
            raise ValueError(
                "ZyteApiParams dependencies must be annotated, "
                "e.g. Annotated[ZyteApiParams, zyte_api_params({...})]."
            )
        cls_params = _from_hashable(cls.__metadata__[0])  # type: ignore[attr-defined]
        if not isinstance(cls_params, dict):
            raise ValueError(
                f"ZyteApiParams dependencies must be annotated with a "
                f"dictionary of Zyte API parameters, ideally through "
                f"zyte_api_params(), but {cls} is annotated with "
                f"{cls.__metadata__[0]!r}."  # type: ignore[attr-defined]
            )
        for key, value in cls_params.items():
            if key == "url":
                raise ValueError(
                    "ZyteApiParams dependencies cannot set the url Zyte API "
                    "parameter, which is always the URL of the request being "
                    "processed."
                )
            if key in params and params[key] != value:
                raise ValueError(
                    f"Multiple different values requested for the {key} Zyte "
                    f"API parameter through ZyteApiParams dependencies: "
                    f"{params[key]!r} and {value!r}."
                )
            params[key] = value
    for key in sorted(
        (params.keys() & _DEPENDENCY_MANAGED_PARAMS) - _warned_dependency_managed_params
    ):
        _warned_dependency_managed_params.add(key)
        logger.warning(
            f"A ZyteApiParams dependency sets the {key} Zyte API parameter, "
            f"which has a dedicated input or annotation. Use that input or "
            f"annotation instead; setting {key} directly may have no effect, "
            f"or make you pay for output that cannot be read."
        )
    return params


def _build_zyte_api_provider_meta(
    to_provide: Set[Callable],
    request: Request,
    crawler: Crawler,
    *,
    provider_params: dict[str, Any] | None = None,
    meta_params: dict[str, Any] | None = None,
    screenshot_requested: bool | None = None,
    http_response_available: bool = False,
    for_fingerprint: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Build Zyte API params for a provider request.

    Returns the params dict and whether browser HTML must be requested.
    """
    if screenshot_requested is None:
        screenshot_requested = Screenshot in to_provide

    html_requested = BrowserResponse in to_provide or BrowserHtml in to_provide

    if provider_params is None:
        provider_params = _get_zyte_api_provider_params(request, crawler)
    if meta_params is None:
        meta_params = _get_zyte_api_meta_params(request)

    zyte_api_meta = dict(provider_params)

    # Parameters from ZyteApiParams dependencies override those from the
    # ZYTE_API_PROVIDER_PARAMS setting, but not those from the
    # zyte_api_provider request metadata key.
    for key, value in _get_zyte_api_dependency_params(to_provide).items():
        if key in meta_params:
            continue
        if for_fingerprint and key not in _FINGERPRINT_PARAM_KEYS:
            continue
        zyte_api_meta[key] = value

    to_provide_stripped: set[type] = set()
    extract_from_seen: dict[str, str] = {}
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
                zyte_api_meta["actions"].append(_from_hashable(action))
            continue
        if cls_stripped is NetworkCapture:
            if not is_typing_annotated(cls):
                raise ValueError(
                    "NetworkCapture dependencies must be annotated, "
                    "e.g. Annotated[NetworkCapture, network_capture([...list of filters...])]."
                )
            zyte_api_meta["networkCapture"] = []
            for f in cls.__metadata__[0]:  # type: ignore[attr-defined]
                zyte_api_meta["networkCapture"].append(_from_hashable(f))
            continue
        if cls_stripped in {CustomAttributes, CustomAttributesValues}:
            custom_attrs_input, custom_attrs_options = cls.__metadata__[0]  # type: ignore[attr-defined]
            zyte_api_meta["customAttributes"] = _from_hashable(custom_attrs_input)
            if custom_attrs_options:
                zyte_api_meta["customAttributesOptions"] = _from_hashable(
                    custom_attrs_options
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
        for extract_from_annotation in ExtractFrom:
            if extract_from_annotation in metadata:
                prev_extract_from = extract_from_seen.get(kw)
                if prev_extract_from and prev_extract_from != extract_from_annotation:
                    raise ValueError(
                        f"Multiple different extractFrom specified for {kw}"
                    )
                extract_from_seen[kw] = extract_from_annotation
                options = zyte_api_meta.setdefault(f"{kw}Options", {})
                options.setdefault("extractFrom", extract_from_annotation.value)
                break

    http_response_needed = (
        AnyResponse in to_provide
        and BrowserResponse not in to_provide
        and BrowserHtml not in to_provide
        and not screenshot_requested
        and not http_response_available
    )

    extract_from: str | None = None
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

    return zyte_api_meta, html_requested


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
        CustomAttributes,
        CustomAttributesValues,
        Geolocation,
        JobPosting,
        JobPostingNavigation,
        NetworkCapture,
        Product,
        ProductList,
        ProductNavigation,
        Screenshot,
        Serp,
        ZyteApiParams,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._should_track_auto_fields = None
        self._tracked_auto_fields = set()

    def is_provided(self, type_: Callable) -> bool:
        return super().is_provided(strip_annotated(type_))

    def _track_auto_fields(self, crawler: Crawler, request: Request, cls: type):
        assert crawler.stats
        if cls not in _ITEM_KEYWORDS:
            return
        if self._should_track_auto_fields is None:
            self._should_track_auto_fields = crawler.settings.getbool(
                "ZYTE_API_AUTO_FIELD_STATS", False
            )
        if self._should_track_auto_fields is False:
            return
        cls = self.injector.registry.page_cls_for_item(request.url, cls) or cls
        if cls in self._tracked_auto_fields:
            return
        self._tracked_auto_fields.add(cls)
        if cls in _ITEM_KEYWORDS:
            field_list = "(all fields)"
        else:
            auto_fields = set()
            for field_name in get_fields_dict(cls):
                if is_auto_field(cls, field_name):  # type: ignore[arg-type]
                    auto_fields.add(field_name)
            field_list = " ".join(sorted(auto_fields))
        cls_fqn = get_fq_class_name(cls)
        crawler.stats.set_value(f"scrapy-zyte-api/auto_fields/{cls_fqn}", field_list)

    async def __call__(
        self, to_provide: Set[Callable], request: Request, crawler: Crawler
    ) -> Sequence[Any]:
        """Makes a Zyte API request to provide BrowserResponse and/or item dependencies."""
        results: list[Any] = []

        http_response = None
        screenshot_requested = Screenshot in to_provide
        for cls in list(to_provide):
            self._track_auto_fields(crawler, request, cast("type", cls))
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

        meta_params = _get_zyte_api_meta_params(request)
        provider_params = _get_zyte_api_provider_params(request, crawler)

        http_response_available = http_response is not None
        zyte_api_meta, html_requested = _get_or_build_zyte_api_provider_meta(
            to_provide,
            request,
            crawler,
            provider_params=provider_params,
            meta_params=meta_params,
            screenshot_requested=screenshot_requested,
            http_response_available=http_response_available,
        )

        api_request = Request(
            url=request.url,
            meta={
                "zyte_api": zyte_api_meta,
                "zyte_api_default_params": False,
            },
            callback=NO_CALLBACK,
        )
        assert crawler.engine
        if _ENGINE_HAS_DOWNLOAD_ASYNC:
            future = cast(
                "Coroutine[None, None, ZyteAPITextResponse]",
                crawler.engine.download_async(api_request),
            )
        else:  # Scrapy < 2.14
            deferred = cast(
                "Deferred[ZyteAPITextResponse]", crawler.engine.download(api_request)
            )
            future = cast(
                "Coroutine[None, None, ZyteAPITextResponse]",
                maybe_deferred_to_future(deferred),
            )
        api_response: ZyteAPITextResponse = await future

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
                actions_result: list[_ActionResult] | None
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
            if cls_stripped is ZyteApiParams and is_typing_annotated(cls):
                result = AnnotatedInstance(
                    ZyteApiParams(dict(zyte_api_meta)),
                    cls.__metadata__,  # type: ignore[attr-defined]
                )
                results.append(result)
                continue
            if cls_stripped is NetworkCapture and is_typing_annotated(cls):
                captured = [
                    CapturedResponse.from_dict(item)
                    for item in api_response.raw_api_response.get("networkCapture", [])
                ]
                result = AnnotatedInstance(NetworkCapture(captured), cls.__metadata__)  # type: ignore[attr-defined]
                results.append(result)
                continue
            if cls_stripped is CustomAttributes and is_typing_annotated(cls):
                custom_attrs_result = api_response.raw_api_response["customAttributes"]
                result = AnnotatedInstance(
                    CustomAttributes(
                        CustomAttributesValues(custom_attrs_result["values"]),
                        CustomAttributesMetadata.from_dict(
                            custom_attrs_result["metadata"]
                        ),
                    ),
                    cls.__metadata__,  # type: ignore[attr-defined]
                )
                results.append(result)
                continue
            if cls_stripped is CustomAttributesValues and is_typing_annotated(cls):
                custom_attrs_result = api_response.raw_api_response["customAttributes"]
                result = AnnotatedInstance(
                    CustomAttributesValues(custom_attrs_result["values"]),
                    cls.__metadata__,  # type: ignore[attr-defined]
                )
                results.append(result)
                continue
            kw = _ITEM_KEYWORDS.get(cls_stripped)
            if not kw:
                continue
            assert issubclass(cls_stripped, Item)
            result = cls_stripped.from_dict(api_response.raw_api_response[kw])
            if is_typing_annotated(cls):
                result = AnnotatedInstance(result, cls.__metadata__)  # type: ignore[attr-defined]
            results.append(result)
        return results
