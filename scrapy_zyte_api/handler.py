import logging

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session

# from zyte_api.aio.errors import RequestError

logger = logging.getLogger("scrapy-zyte-api")


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(self, settings: Settings, crawler: Crawler):
        super().__init__(settings=settings, crawler=crawler)
        self._client: AsyncClient = AsyncClient()
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        # TODO Think about concurrent requests implementation
        # TODO Add custom stats to increase/monitor
        self._stats = crawler.stats
        self._session = create_session()

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        if request.meta.get("zyte_api"):
            return deferred_from_coro(self._download_request(request, spider))
        else:
            return super().download_request(request, spider)

    async def _download_request(self, request: Request, spider: Spider):
        api_data = {"url": request.url, "browserHtml": True}
        api_params = request.meta["zyte_api"]
        if api_params.get("javascript"):
            api_data["javascript"] = api_params["javascript"]
        if api_params.get("geolocation"):
            api_data["geolocation"] = api_params["geolocation"]
        echo_data = api_params.get("echoData")
        # TODO Decide how to validate echoData
        if echo_data:
            api_data["echoData"] = echo_data
        # TODO Check where to pick jobId
        # TODO Handle request errors
        api_response = await self._client.request_raw(api_data, session=self._session)
        body = api_response["browserHtml"].encode("utf-8")
        # TODO Add retrying support
        return Response(
            url=request.url,
            status=api_response["statusCode"],
            body=body,
            request=request
            # API provides no page-request-related headers
        )

    @inlineCallbacks
    def close(self) -> Deferred:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()
