from enum import Enum
from typing import Any, Callable, Dict, List, Sequence, Set, Type
from weakref import WeakKeyDictionary

from andi.typeutils import is_typing_annotated, strip_annotated
from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy_poet import PageObjectInputProvider
from web_poet import BrowserHtml, BrowserResponse
from zyte_common_items import (
    Article,
    ArticleList,
    ArticleNavigation,
    Product,
    ProductList,
    ProductNavigation,
)

from scrapy_zyte_api.responses import ZyteAPITextResponse

try:
    # requires Scrapy >= 2.8
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = None


class ExtractFrom(str, Enum):
    httpResponseBody: str = "httpResponseBody"
    browserHtml: str = "browserHtml"


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
    }

    def __init__(self, injector):
        super().__init__(injector)
        self._cached_instances: WeakKeyDictionary[Request, Dict] = WeakKeyDictionary()

    def update_cache(self, request: Request, mapping: Dict[Type, Any]) -> None:
        if request not in self._cached_instances:
            self._cached_instances[request] = {}
        self._cached_instances[request].update(mapping)

    async def __call__(
        self, to_provide: Set[Callable], request: Request, crawler: Crawler
    ) -> Sequence[Any]:
        """Makes a Zyte API request to provide BrowserResponse and/or item dependencies."""
        # TODO what if ``response`` is already from Zyte API and contains something we need
        results: List[Any] = []

        for cls in list(to_provide):
            item = self._cached_instances.get(request, {}).get(cls)
            if item:
                results.append(item)
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
        }

        zyte_api_meta = crawler.settings.getdict("ZYTE_API_PROVIDER_PARAMS")
        if html_requested:
            zyte_api_meta["browserHtml"] = True

        for cls in to_provide:
            cls_stripped = strip_annotated(cls)
            kw = item_keywords.get(cls_stripped)
            if not kw:
                continue
            zyte_api_meta[kw] = True
            if not is_typing_annotated(cls):
                continue
            metadata = cls.__metadata__
            if cls_stripped == Product:
                for option in ExtractFrom:
                    if option in metadata:
                        product_options = zyte_api_meta.setdefault("productOptions", {})
                        product_options["extractFrom"] = option.value
                        break

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
            self.update_cache(request, {BrowserHtml: html})
        if BrowserResponse in to_provide:
            response = BrowserResponse(
                url=api_response.url,
                status=api_response.status,
                html=html,
            )
            results.append(response)
            self.update_cache(request, {BrowserResponse: response})

        for cls in to_provide:
            cls_stripped = strip_annotated(cls)
            kw = item_keywords.get(cls_stripped)
            if not kw:
                continue
            item = cls_stripped.from_dict(api_response.raw_api_response[kw])
            if is_typing_annotated(cls):
                item.__metadata__ = cls.__metadata__
            results.append(item)
            self.update_cache(request, {cls_stripped: item})
        return results
