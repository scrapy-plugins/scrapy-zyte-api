from typing import Any, Callable, List, Sequence, Set

from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy_poet import PageObjectInputProvider
from web_poet import BrowserHtml, BrowserResponse
from zyte_common_items import Product

from scrapy_zyte_api.responses import ZyteAPITextResponse

try:
    # requires Scrapy >= 2.8
    from scrapy.http.request import NO_CALLBACK
except ImportError:
    NO_CALLBACK = None


class ZyteApiProvider(PageObjectInputProvider):
    name = "zyte_api"

    provided_classes = {BrowserResponse, BrowserHtml, Product}

    async def __call__(
        self, to_provide: Set[Callable], request: Request, crawler: Crawler
    ) -> Sequence[Any]:
        """Makes a Zyte API request to provide BrowserResponse and/or item dependencies."""
        # TODO what if ``response`` is already from Zyte API and contains something we need

        html_requested = BrowserResponse in to_provide or BrowserHtml in to_provide
        item_keywords = {Product: "product"}

        zyte_api_meta = {}
        if html_requested:
            zyte_api_meta["browserHtml"] = True
        for item_type, kw in item_keywords.items():
            if item_type in to_provide:
                zyte_api_meta[kw] = True
        request = Request(
            url=request.url,
            meta={
                "zyte_api": zyte_api_meta,
                "zyte_api_default_params": False,
            },
            callback=NO_CALLBACK,
        )
        api_response: ZyteAPITextResponse = await maybe_deferred_to_future(
            crawler.engine.download(request)
        )

        assert api_response.raw_api_response
        results: List[Any] = []
        if html_requested:
            html = BrowserHtml(api_response.raw_api_response["browserHtml"])
        else:
            html = None
        if BrowserHtml in to_provide:
            results.append(html)
        if BrowserResponse in to_provide:
            results.append(
                BrowserResponse(
                    url=api_response.url,
                    status=api_response.status,
                    html=html,
                )
            )
        for item_type, kw in item_keywords.items():
            if item_type in to_provide:
                results.append(item_type.from_dict(api_response.raw_api_response[kw]))
        return results
