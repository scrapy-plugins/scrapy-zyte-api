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
from zyte_api import AsyncZyteAPI, RequestError
from zyte_api.apikey import NoApiKey

from ._params import _ParamParser
from ._proxy import (
    _BROWSER_INCOMPATIBLE_COOKIE_PARAMS,
    ProxyAggStats,
    ProxyModeError,
    _build_proxy_request,
    _check_for_proxy_error,
    _get_unknown_proxy_mode_headers,
    _has_proxy_mode_headers,
)
from ._request_transport import _resolve_transport
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
    else:  # list
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
        self._user_agent = settings.get("_ZYTE_API_USER_AGENT", USER_AGENT)
        self._proxy_agg_stats = ProxyAggStats()
        self._warned_experimental_proxy = False
        self._warned_experimental_header_transport = False

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    def _auth_type(self) -> str:
        if _X402_SUPPORT:
            return self._client.auth.type
        return "zyte"

    def _auth_key(self) -> str:
        if _X402_SUPPORT:
            return self._client.auth.key
        return self._client.api_key

    def _log_auth(self):
        if _X402_SUPPORT:
            auth_type = (
                "a Zyte API key"
                if self._auth_type() == "zyte"
                else "an Ethereum private key"
            )
            logger.info(f"Using {auth_type} starting with {self._auth_key()[:7]!r}")
        else:
            logger.info(f"Using a Zyte API key starting with {self._auth_key()[:7]!r}")

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
        api_params = self._param_parser.parse(request, final=True)
        if api_params is None:
            return await self._download_via_fallback(request, spider)

        transport = _resolve_transport(
            request,
            api_params,
            self._crawler.settings,
            self._auth_type(),
            self._param_parser._header_transport_enabled(),
        )
        if transport.experimental == "header":
            self._stats.inc_value(
                "scrapy-zyte-api/request/transport/proxy/experimental/header"
            )
            self._warn_experimental_header_transport()
        elif transport.experimental == "transport":
            self._stats.inc_value(
                "scrapy-zyte-api/request/transport/proxy/experimental"
            )
            self._warn_experimental_proxy()
        if transport.effective == "proxy":
            if transport.incompatible:
                # Only reachable when proxy mode was explicitly forced, or when
                # an unknown Zyte-* header kept an "auto" request in proxy mode
                # (its effect cannot be reproduced through the HTTP API). Either
                # way this is a hard error rather than a silent transport
                # downgrade; _resolve_transport already let eligible "auto"
                # requests fall back to the HTTP API.
                raise self._proxy_incompatible_error(
                    request, transport.incompatible, transport.assigned
                )
            self._stats.inc_value("scrapy-zyte-api/request/transport/proxy")
            return await self._download_via_proxy_mode(api_params, request)

        # An "auto" request that resolved to the HTTP API despite carrying
        # Zyte-* headers was parsed as proxy-bound (its headers left untouched);
        # re-parse forcing HTTP API semantics so those headers map to params.
        if transport.assigned == "auto" and _has_proxy_mode_headers(request):
            api_params = self._param_parser.parse(request, final=True, force_http=True)
        self._stats.inc_value("scrapy-zyte-api/request/transport/http")
        return await self._download_via_http_api(api_params, request)

    def _warn_experimental_proxy(self) -> None:
        if self._warned_experimental_proxy:
            return
        self._warned_experimental_proxy = True
        logger.warning(
            "Some requests are eligible for Zyte API proxy mode and would be "
            "sent through it automatically in a future version of "
            "scrapy-zyte-api. However, proxy mode support is currently "
            "experimental and opt-in, so those requests are being sent "
            "through the Zyte API HTTP API instead. To send eligible requests "
            "through proxy mode, set the ZYTE_API_TRANSPORT setting (or the "
            "zyte_api_transport request metadata key; for scrapy-poet "
            "provider requests, the ZYTE_API_PROVIDER_TRANSPORT setting or "
            "the zyte_api_provider_transport request metadata key; for session "
            "initialization requests, the ZYTE_API_SESSION_TRANSPORT setting or "
            "the zyte_api_session_transport request metadata key) to 'auto' "
            "or 'proxy'. To keep using the HTTP API and silence this warning, "
            "set it to 'http' instead. If you enable proxy mode and run into "
            "any issues, please report them at "
            "https://github.com/scrapy-plugins/scrapy-zyte-api/issues."
        )

    def _warn_experimental_header_transport(self) -> None:
        if self._warned_experimental_header_transport:
            return
        self._warned_experimental_header_transport = True
        logger.warning(
            "Some requests carry Zyte-* headers and would be sent through Zyte "
            "API in proxy mode automatically in a future version of "
            "scrapy-zyte-api. However, proxy mode support is currently "
            "experimental and opt-in, so those requests are being sent "
            "through the Zyte API HTTP API instead. To send them through proxy "
            "mode, set the ZYTE_API_HEADER_TRANSPORT_ENABLED setting to True. "
            "To keep these headers from routing requests through Zyte API and "
            "silence this warning, set it to False instead. If you enable "
            "proxy mode and run into any issues, please report them at "
            "https://github.com/scrapy-plugins/scrapy-zyte-api/issues."
        )

    def _proxy_incompatible_error(
        self, request: Request, incompatible: list[str], assigned_transport: str
    ) -> ValueError:
        params = ", ".join(sorted(incompatible))
        cookie_note = self._proxy_cookie_incompatibility_note(incompatible)
        if assigned_transport == "auto":
            # Reached only via an unknown Zyte-* header (see _resolve_auto_transport).
            unknown_headers = ", ".join(
                sorted(_get_unknown_proxy_mode_headers(request))
            )
            return ValueError(
                f"Cannot send {request} via Zyte API proxy mode because the "
                f"following Zyte API parameters are not supported in proxy mode: "
                f"{params}. The request could fall back to the HTTP API, but it "
                f"also defines the following unknown Zyte-* headers, which the "
                f"HTTP API does not support and would silently ignore: "
                f"{unknown_headers}. Remove these headers or the listed "
                f"parameters, or set the 'http' request transport explicitly if "
                f"you do not need them.{cookie_note}"
            )
        return ValueError(
            f"Cannot send {request} via Zyte API proxy mode because the "
            f"following Zyte API parameters are not supported in proxy mode: "
            f"{params}. Remove them, set the corresponding Zyte-* request header "
            f"instead where available, use the 'auto' or 'http' request "
            f"transport, or upgrade scrapy-zyte-api in case proxy mode has since "
            f"added support for them.{cookie_note}"
        )

    @staticmethod
    def _proxy_cookie_incompatibility_note(incompatible: list[str]) -> str:
        """Return an explanatory note when the incompatibility is due to cookie
        parameters combined with browser rendering, or an empty string."""
        cookie_params = sorted(
            p
            for p in incompatible
            if p.rsplit(".", 1)[-1] in _BROWSER_INCOMPATIBLE_COOKIE_PARAMS
        )
        if not cookie_params:
            return ""
        names = ", ".join(cookie_params)
        return (
            f" Note that {names} are supported in proxy mode only without "
            f"browser rendering: with browserHtml, proxy mode cannot represent "
            f"the browser cookie jar (request cookies lose their domain, path "
            f"and flags, and response cookies miss cookies set during "
            f"rendering), so the HTTP API request transport must be used for "
            f"these instead."
        )

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
            if isinstance(retrying, str):  # Scrapy < 2.4 doesn't have this check
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
            self._proxy_url,
            self._auth_key(),
            request,
            api_params,
            user_agent=self._user_agent,
        )
        self._log_proxy_request(proxy_request)
        # The HTTP API path can pass retrying=None and let python-zyte-api fall
        # back to the client's configured policy (``retrying or self.retrying``),
        # but proxy mode drives tenacity directly, so resolve None to that same
        # default here to avoid an AttributeError on ``retrying.wraps``.
        retrying = self._get_request_retrying(request) or self._client.retrying

        start_time = time.time()

        try:
            response = await retrying.wraps(self._attempt_via_proxy)(proxy_request)
            self._proxy_agg_stats.n_success += 1
        except ProxyModeError as error:
            self._proxy_agg_stats.n_fatal_errors += 1
            self._process_request_error(request, error)
            raise
        except Exception:
            self._proxy_agg_stats.n_fatal_errors += 1
            raise
        finally:
            self._set_download_latency(request, time.time() - start_time)
            self._update_stats(self._proxy_stats_params(request, api_params))

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
        # Per-attempt accounting mirrors python-zyte-api's AggStats (see
        # zyte_api.stats.ResponseStats): every counter below is updated once
        # per attempt, including the attempts that tenacity later retries, so
        # that proxy mode stats match the HTTP API ones. n_success and
        # n_fatal_errors (final outcomes) are tracked by the caller instead.
        proxy = self._proxy_agg_stats
        proxy.n_attempts += 1
        start_time = time.time()
        try:
            response = await self._download_via_fallback(
                proxy_request, self._crawler.spider
            )
            assert response is not None
        except Exception as error:
            proxy.n_errors += 1
            proxy.status_codes[0] += 1
            proxy.exception_types[type(error)] += 1
            raise
        try:
            _check_for_proxy_error(response, query={"url": proxy_request.url})
        except ProxyModeError as error:
            proxy.status_codes[error.status] += 1
            if error.status == 429:
                proxy.n_429 += 1
            else:
                proxy.n_errors += 1
            proxy.api_error_types[error.parsed.type] += 1
            raise
        proxy.status_codes[response.status] += 1
        proxy.time_total_stats.push(time.time() - start_time)
        return response

    def _proxy_stats_params(self, request: Request, api_params: dict) -> dict:
        """Return the Zyte API parameters to count in the ``request_args``
        stats for a proxy-mode *request*.

        In proxy mode, ``Zyte-*`` request headers are passed through to the
        proxy endpoint untouched and are not mapped to HTTP API parameters, so
        *api_params* omits them. Re-parse the request with non-final (HTTP API)
        semantics — which maps those headers to their matching parameters
        without emitting the misleading "header dropped" warnings — so that the
        ``request_args`` stats reflect the actual parameters in use (``url``,
        ``httpRequestBody``, ``device``, ``geolocation``, ...) regardless of
        the transport. Parameters that are implicit in proxy mode are included
        too: ``httpResponseBody`` and ``httpResponseHeaders``.
        """
        if _has_proxy_mode_headers(request):
            params = self._param_parser.parse(request) or api_params
        else:
            params = api_params
        params = dict(params)
        params.setdefault("httpResponseHeaders", True)
        return params

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
            k.decode(): (request.headers.get(k) or b"").decode()
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
