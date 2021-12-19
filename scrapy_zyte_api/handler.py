import logging

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro

# from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session

# from zyte_api.aio.errors import RequestError

logger = logging.getLogger("scrapy-zyte-api")


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncClient = None
    ):
        super().__init__(settings=settings, crawler=crawler)
        self._client: AsyncClient = client if client else AsyncClient()
        # verify_installed_reactor(
        #     "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        # )
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
        allowed_keys = {"javascript", "geolocation", "echoData"}
        api_params = request.meta["zyte_api"]
        if not isinstance(api_params, dict):
            raise TypeError(
                "zyte_api parameters in the request meta should be "
                f"provided as dictionary (got {type(api_params)} instead)"
            )
        for key, value in api_params.items():
            if key not in allowed_keys:
                logger.warning(
                    f"Key `{key}` isn't allowed in zyte_api parameters, skipping."
                )
                continue
            # Protect default settings (request url and browserHtml)
            if key in api_data:
                logger.warning(
                    "Key `{key}` is already in zyte_api parameters "
                    f"({api_data[key]}) and can't be overwritten, skipping."
                )
                continue
            # TODO Decide how to validate echoData or do I need to validate it at all?
            api_data[key] = value
        # TODO Check where to pick jobId
        # TODO Handle request errors
        api_response = await self._client.request_raw(api_data, session=self._session)
        self._stats.inc_value("scrapy-zyte-api/request_count")
        body = api_response["browserHtml"].encode("utf-8")
        # TODO Add retrying support?
        return Response(
            url=request.url,
            # TODO Add status code data to the API
            status=200,
            body=body,
            request=request,
            flags=["zyte-api"],
            # API provides no page-request-related headers, so returning no headers
        )

    @inlineCallbacks
    def close(self) -> Deferred:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()
