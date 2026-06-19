from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import ensureDeferred
from zyte_api import AsyncZyteAPI, RequestError, zyte_api_retrying
from zyte_api.apikey import NoApiKey

from ._params import _ParamParser
from ._proxy import (
    ProxyAggStats,
    ProxyModeError,
    _build_proxy_request,
    _check_for_proxy_error,
    _warn_forced_proxy_params,
)
from ._request_mode import _resolve_mode
from .responses import (
    ZyteAPIJsonResponse,
    ZyteAPIProxyJsonResponse,
    ZyteAPIProxyResponse,
    ZyteAPIProxyTextResponse,
    ZyteAPIProxyXmlResponse,
    ZyteAPIResponse,
    ZyteAPITextResponse,
    ZyteAPIXmlResponse,
    _process_proxy_response,
    _process_response,
)
from .utils import (  # type: ignore[attr-defined]
    _AUTOTHROTTLE_DONT_ADJUST_DELAY_SUPPORT,
    _DOWNLOAD_REQUEST_RETURNS_DEFERRED,
    _X402_SUPPORT,
    USER_AGENT,
    _build_from_crawler,
    _close_spider,
    maybe_deferred_to_future,
)

if _DOWNLOAD_REQUEST_RETURNS_DEFERRED:
    from scrapy.utils.defer import deferred_from_coro
    from twisted.internet.defer import Deferred

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.http import Request
    from scrapy.http.response import Response
    from scrapy.settings import Settings
    from tenacity import AsyncRetrying

logger = logging.getLogger(__name__)


def _body_max_size_exceeded(
    body_size: int,
    warnsize: int | None,
    maxsize: int | None,
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
        self,
        settings: Settings,
        crawler: Crawler,
        client: AsyncZyteAPI | None = None,
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
            crawler.zyte_api_client = client  # type: ignore[attr-defined]
        self._client: AsyncZyteAPI = crawler.zyte_api_client  # type: ignore[attr-defined]
        self._log_auth()
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
        assert crawler.stats
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

        self._autothrottle_is_enabled = settings.getbool("AUTOTHROTTLE_ENABLED")

        self._proxy_url = settings.get("ZYTE_API_PROXY_URL", "http://api.zyte.com:8011")
        self._proxy_agg_stats = ProxyAggStats()

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    def _log_auth(self):
        if _X402_SUPPORT:
            auth_type = (
                "a Zyte API key"
                if self._client.auth.type == "zyte"
                else "an Ethereum private key"
            )
            logger.info(
                f"Using {auth_type} starting with {self._client.auth.key[:7]!r}"
            )
        else:
            logger.info(
                f"Using a Zyte API key starting with {self._client.api_key[:7]!r}"
            )

    async def engine_started(self):
        self._session = self._client.session(trust_env=self._trust_env)
        if not self._cookies_enabled:
            return
        assert self._crawler.engine
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
        kwargs = {}
        if api_key := settings.get("ZYTE_API_KEY"):
            kwargs["api_key"] = api_key
        if _X402_SUPPORT and (eth_key := settings.get("ZYTE_API_ETH_KEY")):
            kwargs["eth_key"] = eth_key
        if api_url := settings.get("ZYTE_API_URL"):
            kwargs["api_url"] = api_url
        try:
            return AsyncZyteAPI(
                n_conn=settings.getint("CONCURRENT_REQUESTS"),
                user_agent=settings.get("_ZYTE_API_USER_AGENT", USER_AGENT),
                **kwargs,
            )
        except NoApiKey as ex:
            message = (
                "No authentication data provided. See "
                "https://scrapy-zyte-api.readthedocs.io/en/latest/setup.html#auth"
            )
            logger.warning(message)
            raise NotConfigured(message) from ex

    def _create_handler(self, path: Any) -> Any:
        dhcls = load_object(path)
        return _build_from_crawler(dhcls, self._crawler)

    if _DOWNLOAD_REQUEST_RETURNS_DEFERRED:  # Scrapy < 2.14

        def download_request(
            self, request: Request, spider: Spider
        ) -> Deferred[Response | None]:
            return deferred_from_coro(self._dispatch_request(request, spider))
    else:

        async def download_request(self, request: Request) -> Response | None:  # type: ignore[misc]
            return await self._dispatch_request(request)

    async def _dispatch_request(
        self, request: Request, spider: Spider | None = None
    ) -> Response | None:
        api_params = self._param_parser.parse(request)
        if api_params is None:
            return await self._download_via_fallback(request, spider)

        assigned_mode, effective_mode = _resolve_mode(
            request, api_params, self._crawler.settings, self._client.auth.type
        )
        self._stats.inc_value(f"scrapy-zyte-api/request/mode/{effective_mode}")
        if effective_mode == "proxy":
            if assigned_mode == "proxy":
                _warn_forced_proxy_params(api_params, request)
            return await self._download_via_proxy_mode(api_params, request)

        return await self._download_via_http_api(api_params, request)

    async def _download_via_http_api(
        self, api_params: dict, request: Request
    ) -> (
        ZyteAPITextResponse
        | ZyteAPIXmlResponse
        | ZyteAPIJsonResponse
        | ZyteAPIResponse
        | None
    ):
        self._log_request(api_params)
        retrying = self._get_request_retrying(request)

        start_time = time.time()

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
            self._set_download_latency(request, time.time() - start_time)
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

    def _set_download_latency(self, request: Request, elapsed: float) -> None:
        # If AutoThrottle is enabled, and autothrottle_dont_adjust_delay is not
        # set or not supported, we do not set download_latency, as it would
        # cause AutoThrottle to adjust the download delay of the request slot,
        # and we do not want AutoThrottle to do that for Zyte API slots since
        # Zyte API already handles throttling.
        if not self._autothrottle_is_enabled or (
            _AUTOTHROTTLE_DONT_ADJUST_DELAY_SUPPORT
            and request.meta.get("autothrottle_dont_adjust_delay", False)
        ):
            request.meta["download_latency"] = elapsed

    def _get_request_retrying(self, request: Request) -> AsyncRetrying:
        retrying = request.meta.get("zyte_api_retry_policy")
        if retrying:
            if isinstance(retrying, str):
                retrying = load_object(retrying)
        else:
            retrying = self._retry_policy
        return retrying

    async def _download_via_proxy_mode(
        self,
        api_params: dict[str, Any],
        request: Request,
    ) -> (
        ZyteAPIProxyTextResponse
        | ZyteAPIProxyXmlResponse
        | ZyteAPIProxyJsonResponse
        | ZyteAPIProxyResponse
        | None
    ):
        proxy_request = _build_proxy_request(
            self._proxy_url, self._client.auth.key, request, api_params
        )
        self._log_proxy_request(proxy_request)
        retrying = self._get_request_retrying(request) or zyte_api_retrying

        start_time = time.time()

        try:
            response = await retrying.wraps(self._attempt_via_proxy)(proxy_request)
            self._proxy_agg_stats.n_success += 1
            self._proxy_agg_stats.status_codes[response.status] += 1
        except ProxyModeError as error:
            self._proxy_agg_stats.n_fatal_errors += 1
            self._proxy_agg_stats.n_errors += 1
            self._proxy_agg_stats.status_codes[error.status] += 1
            error_type = error.parsed.type
            self._proxy_agg_stats.api_error_types[error_type] += 1
            self._process_request_error(request, error)
            raise
        except Exception:
            self._proxy_agg_stats.n_errors += 1
            raise
        finally:
            elapsed = time.time() - start_time
            self._proxy_agg_stats.time_total_stats.push(elapsed)
            self._set_download_latency(request, elapsed)
            self._update_stats(api_params)

        proxy_response = _process_proxy_response(
            response, request, proxy_request, api_params
        )

        if _body_max_size_exceeded(
            len(proxy_response.body),
            self._default_warnsize,
            self._default_maxsize,
            request.url,
        ):
            return None

        return proxy_response

    async def _attempt_via_proxy(self, proxy_request: Request) -> Response:
        self._proxy_agg_stats.n_attempts += 1
        response = await self._download_via_fallback(
            proxy_request, self._crawler.spider
        )
        _check_for_proxy_error(response, query={"url": proxy_request.url})
        return response

    def _update_stats(self, api_params):
        prefix = "scrapy-zyte-api"
        for arg in api_params:
            if arg == "experimental":
                for subarg in api_params[arg]:
                    self._stats.inc_value(f"{prefix}/request_args/{arg}.{subarg}")
            else:
                self._stats.inc_value(f"{prefix}/request_args/{arg}")

        http = self._client.agg_stats
        proxy = self._proxy_agg_stats

        for field, val in vars(http).items():
            if not field.startswith("n_") or not isinstance(val, int):
                continue
            stat_key = field[2:]  # strip "n_" prefix
            proxy_val = getattr(proxy, field, None)
            if proxy_val is None:
                proxy_val = 0
            self._stats.set_value(f"{prefix}/{stat_key}", val + proxy_val)

        n_processed = http.n_processed + (proxy.n_success + proxy.n_fatal_errors)
        self._stats.set_value(f"{prefix}/processed", n_processed)

        n_attempts = http.n_attempts + proxy.n_attempts
        n_errors = http.n_errors + proxy.n_errors
        n_429 = http.n_429 + proxy.n_429
        n_success = http.n_success + proxy.n_success
        self._stats.set_value(
            f"{prefix}/error_ratio",
            n_errors / n_attempts if n_attempts else 0.0,
        )
        self._stats.set_value(
            f"{prefix}/success_ratio",
            n_success / n_processed if n_processed else 0.0,
        )
        self._stats.set_value(
            f"{prefix}/throttle_ratio",
            n_429 / n_attempts if n_attempts else 0.0,
        )

        for source, target in (
            ("connect", "connection"),
            ("total", "response"),
        ):
            combined = getattr(http, f"time_{source}_stats") + getattr(
                proxy, f"time_{source}_stats"
            )
            self._stats.set_value(
                f"{prefix}/mean_{target}_seconds",
                combined.mean(),
            )

        combined_error_types = http.api_error_types + proxy.api_error_types
        for error_type, count in combined_error_types.items():
            error_type = error_type or "/<empty>"  # noqa: PLW2901
            if not error_type.startswith("/"):
                error_type = f"/{error_type}"  # noqa: PLW2901
            self._stats.set_value(f"{prefix}/error_types{error_type}", count)

        for counter in ("exception_types", "status_codes"):
            combined = getattr(http, counter) + getattr(proxy, counter)
            for key, value in combined.items():
                self._stats.set_value(f"{prefix}/{counter}/{key}", value)

    def _process_request_error(self, request, error):
        detail = (error.parsed.data or {}).get("detail", error.message)
        logger.debug(
            f"Got Zyte API error (status={error.status}, "
            f"type={error.parsed.type!r}, request_id={error.request_id!r}) "
            f"while processing URL ({request.url}): {detail}"
        )
        assert self._crawler
        assert self._crawler.engine
        assert self._crawler.spider
        for status, error_type, close_reason in (
            (401, "/auth/key-not-found", "zyte_api_bad_key"),
            (403, "/auth/account-suspended", "zyte_api_suspended_account"),
        ):
            if error.status == status and error.parsed.type == error_type:
                _close_spider(self._crawler, close_reason)
                return

    def _log_proxy_request(self, request: Request):
        proxy_headers = {
            k.decode(): request.headers.get(k).decode()
            for k in request.headers
            if k.lower().startswith(b"zyte-")
        }
        self._log_request(proxy_headers, is_proxy=True, url=request.url)

    def _log_request(self, params, *, is_proxy: bool = False, url: str = ""):
        if not self._must_log_request:
            return
        params = self._truncate_params(params)
        if is_proxy:
            logger.debug(f"Sending Zyte API proxy request: {url} {json.dumps(params)}")
        else:
            logger.debug(f"Sending Zyte API extract request: {json.dumps(params)}")

    def _truncate_params(self, params):
        if self._truncate_limit == 0:
            return params
        params = deepcopy(params)
        _truncate(params, self._truncate_limit)
        return params

    async def _download_via_fallback(
        self, request: Request, spider: Spider | None = None
    ) -> Response | None:
        assert self._fallback_handler
        if _DOWNLOAD_REQUEST_RETURNS_DEFERRED:
            d = self._fallback_handler.download_request(request, spider)
            return await maybe_deferred_to_future(d)
        return await self._fallback_handler.download_request(request)

    if _DOWNLOAD_REQUEST_RETURNS_DEFERRED:

        def close(self) -> Deferred:
            async def _close():
                if self._fallback_handler and hasattr(self._fallback_handler, "close"):
                    await self._fallback_handler.close()
                await self._close()

            return ensureDeferred(_close())

    else:

        async def close(self) -> None:  # type: ignore[misc]
            if self._fallback_handler and hasattr(self._fallback_handler, "close"):
                await self._fallback_handler.close()
            await self._close()

    async def _close(self) -> None:
        await self._session.close()


class ScrapyZyteAPIDownloadHandler(_ScrapyZyteAPIBaseDownloadHandler):
    def __init__(
        self,
        settings: Settings,
        crawler: Crawler,
        client: AsyncZyteAPI | None = None,
    ):
        super().__init__(settings, crawler, client)
        self._fallback_handler = self._create_handler(
            "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler"
        )


class ScrapyZyteAPIHTTPDownloadHandler(_ScrapyZyteAPIBaseDownloadHandler):
    def __init__(
        self,
        settings: Settings,
        crawler: Crawler,
        client: AsyncZyteAPI | None = None,
    ):
        super().__init__(settings, crawler, client)
        self._fallback_handler = self._create_handler(
            settings.get(
                "ZYTE_API_FALLBACK_HTTP_HANDLER",
                settings.getwithbase("DOWNLOAD_HANDLERS")["http"],
            )
        )


class ScrapyZyteAPIHTTPSDownloadHandler(_ScrapyZyteAPIBaseDownloadHandler):
    def __init__(
        self,
        settings: Settings,
        crawler: Crawler,
        client: AsyncZyteAPI | None = None,
    ):
        super().__init__(settings, crawler, client)
        self._fallback_handler = self._create_handler(
            settings.get(
                "ZYTE_API_FALLBACK_HTTPS_HANDLER",
                settings.getwithbase("DOWNLOAD_HANDLERS")["https"],
            )
        )
