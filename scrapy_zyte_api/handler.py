from aiohttp import ClientSession
from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.http import Request, Response
from scrapy.responsetypes import responsetypes
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from twisted.internet.defer import Deferred, inlineCallbacks


# class APIContextManager:
#     async def __aenter__(self):
#         self._session = aiohttp.ClientSession()
#         return self
#
#     async def __aexit__(self, *err):
#         await self._session.close()
#         self._session = None
#
#     async def fetch(self, url):
#         async with self._session.get(url) as resp:
#             resp.raise_for_status()
#             return await resp.read()


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(self, settings: Settings, crawler: Crawler):
        print('*'*500)
        print(type(settings))
        super().__init__(settings=settings, crawler=crawler)
        self._session: ClientSession = ClientSession()

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        return deferred_from_coro(self._download_request(request, spider))

    async def _download_request(self, request: Request, spider: Spider):
        url = "https://books.toscrape.com/catalogue/sapiens-a-brief-history-of-humankind_996/index.html"
        aio_response = await self._session.get(url)
        body = await aio_response.read()
        response_class = responsetypes.from_args(headers={}, url=request.url, body=body)
        return response_class(
            url=request.url,
            status=aio_response.status,
            headers={},
            body=body,
            request=request
        )

    @inlineCallbacks
    def close(self) -> Deferred:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        print('*' * 50)
        print("Closing downloader handler")
