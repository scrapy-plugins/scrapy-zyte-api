import os

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.http import Request, Response
from scrapy.responsetypes import responsetypes
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(self, settings: Settings, crawler: Crawler):
        super().__init__(settings=settings, crawler=crawler)
        self._client: AsyncClient = AsyncClient()
        # TODO Think about concurrent requests implementation
        # TODO Think about sessions reusing

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        return deferred_from_coro(self._download_request(request, spider))

    async def _download_request(self, request: Request, spider: Spider):
        api_response = await self._client.request_raw({
            'url': request.url,
            'browserHtml': True
        })
        body = api_response["browserHtml"].encode("utf-8")
        # TODO Get headers somewhere? Or return just HTML (base Response) every time?
        response_class = responsetypes.from_args(headers=request.headers, url=request.url, body=body)
        return response_class(
            url=request.url,
            # TODO Get headers and status somewhere?
            status=200,
            headers={},
            body=body,
            request=request
        )

    @inlineCallbacks
    def close(self) -> Deferred:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        # TODO Close ssession here if it could be reused
        # await self._session.close()
        pass
