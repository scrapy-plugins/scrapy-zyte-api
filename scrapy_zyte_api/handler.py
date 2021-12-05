from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.http import Request
from scrapy.responsetypes import responsetypes
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(self, settings: Settings, crawler: Crawler):
        super().__init__(settings=settings, crawler=crawler)
        self._client: AsyncClient = AsyncClient()
        # TODO Think about concurrent requests implementation
        # TODO Think about sessions reusing
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        # TODO Add custom stats to increase/monitor
        self.stats = crawler.stats

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        if request.meta.get("zyte_api"):
            return deferred_from_coro(self._download_request(request, spider))
        else:
            return super().download_request(request, spider)

    async def _download_request(self, request: Request, spider: Spider):
        # TODO Add input validation through openapi schema or similar
        # https://github.com/zytedata/zde-api-server/blob/master/server/src/main/resources/openapi/openapi.yaml
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
        api_response = await self._client.request_raw(api_data)
        body = api_response["browserHtml"].encode("utf-8")
        # TODO Could the response be different from default Response (just HTML)?
        response_class = responsetypes.from_args(
            headers=request.headers, url=request.url, body=body
        )
        if echo_data:
            response_class.meta = api_response["echoData"]
        return response_class(
            url=request.url,
            # TODO Get headers and status somewhere or stick with default ones?
            status=200,
            headers={},
            body=body,
            request=request,
        )

    @inlineCallbacks
    def close(self) -> Deferred:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        # TODO Close ssession here if it could be reused
        # await self._session.close()
        pass
