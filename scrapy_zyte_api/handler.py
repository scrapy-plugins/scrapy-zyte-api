import json
import logging
from copy import deepcopy
from typing import Any, Generator, Optional, Union

from scrapy import Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api import AsyncZyteAPI, RequestError
from zyte_api.apikey import NoApiKey
from zyte_api.constants import API_URL

from ._params import _ParamParser
from .responses import ZyteAPIResponse, ZyteAPITextResponse, _process_response
from .utils import USER_AGENT

logger = logging.getLogger(__name__)


def _body_max_size_exceeded(
    body_size: int,
    warnsize: Optional[int],
    maxsize: Optional[int],
    request_url: str,
) -> bool:
    if warnsize and body_size > warnsize:
        logger.warning(
            f"Actual response size {body_size} larger than "
            f"download warn size {warnsize} in request {request_url}."
        )

    if maxsize and body_size > maxsize:
        logger.warning(
            f"Dropping the response for {request_url}: actual response size "
            f"{body_size} larger than download max size {maxsize}."
        )
        return True
    return False


def _truncate_str(obj, index, text, limit):
    if len(text) <= limit:
        return
    obj[index] = text[: limit - 1] + "..."


def _truncate(obj, limit):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                _truncate_str(obj, key, value, limit)
            elif isinstance(value, (list, dict)):
                _truncate(value, limit)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            if isinstance(value, str):
                _truncate_str(obj, index, value, limit)
            elif isinstance(value, (list, dict)):
                _truncate(value, limit)


def _load_retry_policy(settings):
    policy = settings.get("ZYTE_API_RETRY_POLICY")
    if policy:
        policy = load_object(policy)
    return policy


class _ScrapyZyteAPIBaseDownloadHandler:
    lazy = False

    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncZyteAPI = None
    ):
        if not settings.getbool("ZYTE_API_ENABLED", True):
            raise NotConfigured(
                "Zyte API is disabled. Set ZYTE_API_ENABLED to True to enable it."
            )
        if not hasattr(crawler, "zyte_api_client"):
            if not client:
                client = self._build_client(settings)
            # We keep the client in the crawler object to prevent multiple,
            # duplicate clients with the same settings to be used.
            # https://github.com/scrapy-plugins/scrapy-zyte-api/issues/58
            crawler.zyte_api_client = client
        self._client: AsyncZyteAPI = crawler.zyte_api_client
        logger.info("Using a Zyte API key starting with %r", self._client.api_key[:7])
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )
        self._cookies_enabled = settings.getbool("COOKIES_ENABLED")
        self._cookie_jars = None
        self._cookie_mw_cls = load_object(
            settings.get(
                "ZYTE_API_COOKIE_MIDDLEWARE",
                "scrapy.downloadermiddlewares.cookies.CookiesMiddleware",
            )
        )
        self._param_parser = _ParamParser(crawler)
        self._retry_policy = _load_retry_policy(settings)
        self._stats = crawler.stats
        self._must_log_request = settings.getbool("ZYTE_API_LOG_REQUESTS", False)
        self._truncate_limit = settings.getint("ZYTE_API_LOG_REQUESTS_TRUNCATE", 64)
        if self._truncate_limit < 0:
            raise ValueError(
                f"The value of the ZYTE_API_LOG_REQUESTS_TRUNCATE setting "
                f"({self._truncate_limit}) is invalid. It must be 0 or a "
                f"positive integer."
            )
        self._default_maxsize = settings.getint("DOWNLOAD_MAXSIZE")
        self._default_warnsize = settings.getint("DOWNLOAD_WARNSIZE")

        crawler.signals.connect(self.engine_started, signal=signals.engine_started)
        self._crawler = crawler
        self._fallback_handler = None
        self._trust_env = settings.getbool("ZYTE_API_USE_ENV_PROXY")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    async def engine_started(self):
        self._session = self._client.session(trust_env=self._trust_env)
        if not self._cookies_enabled:
            return
        for middleware in self._crawler.engine.downloader.middleware.middlewares:
            if isinstance(middleware, self._cookie_mw_cls):
                self._cookie_jars = middleware.jars
                self._param_parser._cookie_jars = self._cookie_jars
                return
        middleware_path = (
            f"{self._cookie_mw_cls.__module__}.{self._cookie_mw_cls.__qualname__}"
        )
        raise RuntimeError(
            f"Could not find a configured downloader middleware that is an "
            f"instance of {middleware_path} (see ZYTE_API_COOKIE_MIDDLEWARE)."
        )

    @staticmethod
    def _build_client(settings):
        try:
            return AsyncZyteAPI(
                # To allow users to have a key defined in Scrapy settings and
                # in a environment variable, and be able to cause the
                # environment variable to be used instead of the setting by
                # overriding the setting on the command-line to be an empty
                # string, we do not support setting empty string keys through
                # settings.
                api_key=settings.get("ZYTE_API_KEY") or None,
                api_url=settings.get("ZYTE_API_URL") or API_URL,
                n_conn=settings.getint("CONCURRENT_REQUESTS"),
                user_agent=settings.get("_ZYTE_API_USER_AGENT", default=USER_AGENT),
            )
        except NoApiKey:
            logger.warning(
                "'ZYTE_API_KEY' must be set in the spider settings or env var "
                "in order for ScrapyZyteAPIDownloadHandler to work."
            )
            raise NotConfigured(
                "Your Zyte API key is not set. Set ZYTE_API_KEY to your API key."
            )

    def _create_handler(self, path: Any) -> Any:
        dhcls = load_object(path)
        return create_instance(dhcls, settings=None, crawler=self._crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        api_params = self._param_parser.parse(request)
        if api_params is not None:
            return deferred_from_coro(
                self._download_request(api_params, request, spider)
            )
        assert self._fallback_handler
        return self._fallback_handler.download_request(request, spider)

    def _update_stats(self, api_params):
        prefix = "scrapy-zyte-api"
        for arg in api_params:
            if arg == "experimental":
                for subarg in api_params[arg]:
                    self._stats.inc_value(f"{prefix}/request_args/{arg}.{subarg}")
            else:
                self._stats.inc_value(f"{prefix}/request_args/{arg}")
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
            if isinstance(retrying, str):  # Scrapy < 2.4 doesn't have this check
                retrying = load_object(retrying)
        else:
            retrying = self._retry_policy
        self._log_request(api_params)

        try:
            api_response = await self._session.get(api_params, retrying=retrying)
        except RequestError as error:
            self._process_request_error(request, error)
            raise
        except Exception as er:
            logger.debug(
                f"Got an error when processing Zyte API request ({request.url}): {er}"
            )
            raise
        finally:
            self._update_stats(api_params)

        response = _process_response(
            api_response=api_response, request=request, cookie_jars=self._cookie_jars
        )
        if response and _body_max_size_exceeded(
            len(response.body),
            self._default_warnsize,
            self._default_maxsize,
            request.url,
        ):
            return None

        return response

    def _process_request_error(self, request, error):
        detail = (error.parsed.data or {}).get("detail", error.message)
        logger.debug(
            f"Got Zyte API error (status={error.status}, "
            f"type={error.parsed.type!r}, request_id={error.request_id!r}) "
            f"while processing URL ({request.url}): {detail}"
        )
        for status, error_type, close_reason in (
            (401, "/auth/key-not-found", "zyte_api_bad_key"),
            (403, "/auth/account-suspended", "zyte_api_suspended_account"),
        ):
            if error.status == status and error.parsed.type == error_type:
                self._crawler.engine.close_spider(self._crawler.spider, close_reason)
                return

    def _log_request(self, params):
        if not self._must_log_request:
            return
        params = self._truncate_params(params)
        logger.debug(f"Sending Zyte API extract request: {json.dumps(params)}")

    def _truncate_params(self, params):
        if self._truncate_limit == 0:
            return params
        params = deepcopy(params)
        _truncate(params, self._truncate_limit)
        return params

    @inlineCallbacks
    def close(self) -> Generator:
        if self._fallback_handler:
            yield self._fallback_handler.close()
        yield deferred_from_coro(self._close())

    async def _close(self) -> None:  # NOQA
        await self._session.close()


class ScrapyZyteAPIDownloadHandler(_ScrapyZyteAPIBaseDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncZyteAPI = None
    ):
        super().__init__(settings, crawler, client)
        self._fallback_handler = self._create_handler(
            "scrapy.core.downloader.handlers.http.HTTPDownloadHandler"
        )


class ScrapyZyteAPIHTTPDownloadHandler(_ScrapyZyteAPIBaseDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncZyteAPI = None
    ):
        super().__init__(settings, crawler, client)
        self._fallback_handler = self._create_handler(
            settings.get("ZYTE_API_FALLBACK_HTTP_HANDLER")
        )


class ScrapyZyteAPIHTTPSDownloadHandler(_ScrapyZyteAPIBaseDownloadHandler):
    def __init__(
        self, settings: Settings, crawler: Crawler, client: AsyncZyteAPI = None
    ):
        super().__init__(settings, crawler, client)
        self._fallback_handler = self._create_handler(
            settings.get("ZYTE_API_FALLBACK_HTTPS_HANDLER")
        )
