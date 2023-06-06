from typing import Any, Callable, Sequence, Set

from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy_poet import PageObjectInputProvider
from web_poet import BrowserResponse
from zyte_common_items import Product

from scrapy_zyte_api.responses import ZyteAPITextResponse

try:
    # requires Scrapy >= 2.8
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = None


class ZyteApiProvider(PageObjectInputProvider):
    name = "zyte_api"

    provided_classes = {BrowserResponse, Product}

    async def __call__(
        self, to_provide: Set[Callable], request: Request, crawler: Crawler
    ) -> Sequence[Any]:
        """Makes a Zyte API request to provide BrowserResponse and/or item dependencies."""

        # TODO what if ``response`` is already from Zyte API and contains something we need
        zyte_api_meta = {}
        if BrowserResponse in to_provide:
            zyte_api_meta["browserHtml"] = True
        if Product in to_provide:
            zyte_api_meta["product"] = True
        request = Request(
            url=request.url,
            meta={
                "zyte_api": zyte_api_meta,
                "zyte_api_default_params": False,
            },
            dont_filter=True,
            callback=NO_CALLBACK,
        )
        api_response: ZyteAPITextResponse = await maybe_deferred_to_future(
            crawler.engine.download(request)
        )
        assert api_response.raw_api_response
        results = []
        if BrowserResponse in to_provide:
            results.append(
                BrowserResponse(
                    url=api_response.url,
                    status=api_response.status,
                    html=api_response.raw_api_response["browserHtml"],
                )
            )
        if Product in to_provide:
            results.append(Product.from_dict(api_response.raw_api_response["product"]))
        return results
