import json
import logging
import os
from base64 import b64decode
from typing import Any, Dict, Generator, List, Optional

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response, TextResponse
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session
from zyte_api.aio.errors import RequestError

logger = logging.getLogger(__name__)


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncClient = None
    ):
        super().__init__(settings=settings, crawler=crawler)
        self._client: AsyncClient = client if client else AsyncClient()
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        self._stats = crawler.stats
        self._job_id = crawler.settings.get("JOB")
        self._session = create_session()
        self._encoding = "utf-8"

    @classmethod
    def from_crawler(cls, crawler):
        zyte_api_key = crawler.settings.get("ZYTE_API_KEY") or os.getenv("ZYTE_API_KEY")
        if not zyte_api_key:
            logger.warning(
                "'ZYTE_API_KEY' must be set in the spider settings or env var "
                "in order for ScrapyZyteAPIDownloadHandler to work."
            )
            raise NotConfigured

        logger.info(f"Using Zyte API Key: {zyte_api_key[:7]}")
        client = AsyncClient(api_key=zyte_api_key)
        return cls(crawler.settings, crawler, client)

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        if request.meta.get("zyte_api"):
            return deferred_from_coro(self._download_request(request, spider))
        else:
            return super().download_request(request, spider)

    async def _download_request(self, request: Request, spider: Spider) -> Response:
        api_params: Dict[str, Any] = request.meta["zyte_api"]
        if not isinstance(api_params, dict):
            logger.error(
                "zyte_api parameters in the request meta should be "
                f"provided as dictionary, got {type(api_params)} instead ({request.url})."
            )
            raise IgnoreRequest()
        # Define url by default
        api_data = {**{"url": request.url}, **api_params}
        if self._job_id is not None:
            api_data["jobId"] = self._job_id
        try:
            api_response = await self._client.request_raw(
                api_data, session=self._session
            )
        except RequestError as er:
            error_message = self._get_request_error_message(er)
            logger.error(
                f"Got Zyte API error ({er.status}) while processing URL ({request.url}): {error_message}"
            )
            raise IgnoreRequest()
        except Exception as er:
            logger.error(
                f"Got an error when processing Zyte API request ({request.url}): {er}"
            )
            raise IgnoreRequest()
        self._stats.inc_value("scrapy-zyte-api/request_count")
        headers = self._prepare_headers(api_response.get("httpResponseHeaders"))
        # browserHtml and httpResponseBody are not allowed at the same time,
        # but at least one of them should be present
        if api_response.get("browserHtml"):
            # Using TextResponse because browserHtml always returns a browser-rendered page
            # even when requesting files (like images)
            return TextResponse(
                url=api_response["url"],
                status=200,
                body=api_response["browserHtml"].encode(self._encoding),
                encoding=self._encoding,
                request=request,
                flags=["zyte-api"],
                headers=headers,
            )
        else:
            return Response(
                url=api_response["url"],
                status=200,
                body=b64decode(api_response["httpResponseBody"]),
                request=request,
                flags=["zyte-api"],
                headers=headers,
            )

    @inlineCallbacks
    def close(self) -> Generator:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()

    @staticmethod
    def _get_request_error_message(error: RequestError) -> str:
        if hasattr(error, "message"):
            base_message = error.message
        else:
            base_message = str(error)
        if not hasattr(error, "response_content"):
            return base_message
        try:
            error_data = json.loads(error.response_content.decode("utf-8"))
        except (AttributeError, TypeError, ValueError):
            return base_message
        if error_data.get("detail"):
            return error_data["detail"]
        return base_message

    @staticmethod
    def _prepare_headers(init_headers: Optional[List[Dict[str, str]]]):
        if not init_headers:
            return None
        return {h["name"]: h["value"] for h in init_headers}
