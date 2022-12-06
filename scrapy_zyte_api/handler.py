import logging
from typing import Generator, Optional, Union

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session
from zyte_api.aio.errors import RequestError
from zyte_api.apikey import NoApiKey
from zyte_api.constants import API_URL

from ._params import _ParamParser
from .responses import ZyteAPIResponse, ZyteAPITextResponse, _process_response

logger = logging.getLogger(__name__)


def _load_retry_policy(settings):
    policy = settings.get("ZYTE_API_RETRY_POLICY")
    if policy:
        policy = load_object(policy)
    return policy


class ScrapyZyteAPIDownloadHandler(HTTPDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncClient = None
    ):
        super().__init__(settings=settings, crawler=crawler)
        if not settings.getbool("ZYTE_API_ENABLED", True):
            raise NotConfigured
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
        logger.info("Using a Zyte API key starting with %r", self._client.api_key[:7])
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        self._param_parser = _ParamParser(settings)
        self._retry_policy = _load_retry_policy(settings)
        self._stats = crawler.stats
        self._session = create_session(connection_pool_size=self._client.n_conn)

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        api_params = self._param_parser.parse(request)
        if api_params is not None:
            return deferred_from_coro(
                self._download_request(api_params, request, spider)
            )
        return super().download_request(request, spider)

    def _update_stats(self):
        prefix = "scrapy-zyte-api"
        for stat in (
            "429",
            "attempts",
            "errors",
            "fatal_errors",
            "processed",
            "success",
        ):
            self._stats.set_value(
                f"{prefix}/{stat}",
                getattr(self._client.agg_stats, f"n_{stat}"),
            )
        for stat in (
            "error_ratio",
            "success_ratio",
            "throttle_ratio",
        ):
            self._stats.set_value(
                f"{prefix}/{stat}",
                getattr(self._client.agg_stats, stat)(),
            )
        for source, target in (
            ("connect", "connection"),
            ("total", "response"),
        ):
            self._stats.set_value(
                f"{prefix}/mean_{target}_seconds",
                getattr(self._client.agg_stats, f"time_{source}_stats").mean(),
            )

        for error_type, count in self._client.agg_stats.api_error_types.items():
            error_type = error_type or "/<empty>"
            if not error_type.startswith("/"):
                error_type = f"/{error_type}"
            self._stats.set_value(f"{prefix}/error_types{error_type}", count)

        for counter in (
            "exception_types",
            "status_codes",
        ):
            for key, value in getattr(self._client.agg_stats, counter).items():
                self._stats.set_value(f"{prefix}/{counter}/{key}", value)

    async def _download_request(
        self, api_params: dict, request: Request, spider: Spider
    ) -> Optional[Union[ZyteAPITextResponse, ZyteAPIResponse]]:
        # Define url by default
        retrying = request.meta.get("zyte_api_retry_policy")
        if retrying:
            retrying = load_object(retrying)
        else:
            retrying = self._retry_policy
        try:
            api_response = await self._client.request_raw(
                api_params,
                session=self._session,
                retrying=retrying,
            )
        except RequestError as er:
            error_detail = (er.parsed.data or {}).get("detail", er.message)
            logger.error(
                f"Got Zyte API error (status={er.status}, type={er.parsed.type!r}) "
                f"while processing URL ({request.url}): {error_detail}"
            )
            raise
        except Exception as er:
            logger.error(
                f"Got an error when processing Zyte API request ({request.url}): {er}"
            )
            raise
        finally:
            self._update_stats()

        return _process_response(api_response, request)

    @inlineCallbacks
    def close(self) -> Generator:
        yield super().close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()
