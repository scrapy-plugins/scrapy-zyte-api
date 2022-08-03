import logging
from typing import Any, Dict, Generator, Optional, Union

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session
from zyte_api.aio.errors import RequestError
from zyte_api.apikey import NoApiKey
from zyte_api.constants import API_URL

from .responses import ZyteAPIResponse, ZyteAPITextResponse, _process_response

logger = logging.getLogger(__name__)


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncClient = None
    ):
        super().__init__(settings=settings, crawler=crawler)
        if not client:
            try:
                client = AsyncClient(
                    # To allow users to have a key defined in Scrapy settings
                    # and in a environment variable, and be able to cause the
                    # environment variable to be used instead of the setting by
                    # overriding the setting on the command-line to be an empty
                    # string, we do not support setting empty string keys
                    # through settings.
                    api_key=settings.get("ZYTE_API_KEY") or None,
                    api_url=settings.get("ZYTE_API_URL") or API_URL,
                    n_conn=settings.getint("CONCURRENT_REQUESTS"),
                )
            except NoApiKey:
                logger.warning(
                    "'ZYTE_API_KEY' must be set in the spider settings or env var "
                    "in order for ScrapyZyteAPIDownloadHandler to work."
                )
                raise NotConfigured
        self._client: AsyncClient = client
        logger.info(
            "Using a Zyte Data API key starting with %r", self._client.api_key[:7]
        )
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        self._stats = crawler.stats
        self._job_id = crawler.settings.get("JOB")
        self._zyte_api_default_params = settings.getdict("ZYTE_API_DEFAULT_PARAMS")
        self._session = create_session(connection_pool_size=self._client.n_conn)
        self._retry_policy = settings.get("ZYTE_API_RETRY_POLICY")

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        api_params = self._prepare_api_params(request)
        if api_params:
            return deferred_from_coro(
                self._download_request(api_params, request, spider)
            )
        return super().download_request(request, spider)

    def _prepare_api_params(self, request: Request) -> Optional[dict]:
        meta_params = request.meta.get("zyte_api")
        if not meta_params and meta_params != {}:
            return None

        if meta_params is True:
            meta_params = {}

        api_params: Dict[str, Any] = self._zyte_api_default_params or {}
        try:
            api_params.update(meta_params)
        except TypeError:
            logger.error(
                f"zyte_api parameters in the request meta should be "
                f"provided as dictionary, got {type(request.meta.get('zyte_api'))} "
                f"instead ({request.url})."
            )
            raise IgnoreRequest()
        return api_params

    def _update_stats(self):
        prefix = "scrapy-zyte-api"
        for stat in (
            '429',
            'attempts',
            'errors',
            'fatal_errors',
            'processed',
            'success',
        ):
            self._stats.set_value(
                f"{prefix}/{stat}",
                getattr(self._client.agg_stats, f"n_{stat}"),
            )
        for stat in (
            'error_ratio',
            'success_ratio',
            'throttle_ratio',
        ):
            self._stats.set_value(
                f"{prefix}/{stat}",
                getattr(self._client.agg_stats, stat)(),
            )
        for source, target in (
            ('connect', 'connection'),
            ('total', 'response'),
        ):
            self._stats.set_value(
                f"{prefix}/mean_{target}_seconds",
                getattr(self._client.agg_stats, f"time_{source}_stats").mean(),
            )

        for error_type, count in self._client.agg_stats.api_error_types.items():
            error_type = error_type or "/<empty>"
            self._stats.set_value(f"{prefix}/error_types{error_type}", count)

        for counter in ('exception_types', 'status_codes',):
            for key, value in getattr(self._client.agg_stats, counter).items():
                self._stats.set_value(f"{prefix}/{counter}/{key}", value)

    async def _download_request(
        self, api_params: dict, request: Request, spider: Spider
    ) -> Optional[Union[ZyteAPITextResponse, ZyteAPIResponse]]:
        # Define url by default
        api_data = {**{"url": request.url}, **api_params}
        if self._job_id is not None:
            api_data["jobId"] = self._job_id
        retrying = request.meta.get("zyte_api_retry_policy") or self._retry_policy
        try:
            api_response = await self._client.request_raw(
                api_data,
                session=self._session,
                retrying=retrying,
            )
        except RequestError as er:
            error_detail = (er.parsed.data or {}).get("detail", er.message)
            logger.error(
                f"Got Zyte API error (status={er.status}, type={er.parsed.type!r}) "
                f"while processing URL ({request.url}): {error_detail}"
            )
            raise IgnoreRequest()
        except Exception as er:
            logger.error(
                f"Got an error when processing Zyte API request ({request.url}): {er}"
            )
            raise IgnoreRequest()
        finally:
            self._update_stats()

        return _process_response(api_response, request)

    @inlineCallbacks
    def close(self) -> Generator:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()
