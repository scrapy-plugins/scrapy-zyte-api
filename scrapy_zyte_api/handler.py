import logging
from base64 import b64decode, b64encode
from copy import copy
from typing import Any, Dict, Generator, Mapping, Optional, Set, Union
from warnings import warn

from scrapy import Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Request
from scrapy.settings import Settings
from scrapy.settings.default_settings import DEFAULT_REQUEST_HEADERS
from scrapy.settings.default_settings import USER_AGENT as DEFAULT_USER_AGENT
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.misc import load_object
from scrapy.utils.reactor import verify_installed_reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from zyte_api.aio.client import AsyncClient, create_session
from zyte_api.aio.errors import RequestError
from zyte_api.apikey import NoApiKey
from zyte_api.constants import API_URL

from .responses import ZyteAPIResponse, ZyteAPITextResponse, _process_response

logger = logging.getLogger(__name__)


_DEFAULT_API_PARAMS = {
    "browserHtml": False,
    "screenshot": False,
}


def _iter_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    parameter: str,
):
    headers = api_params.get(parameter)
    if headers is not None:
        logger.warning(
            f"Request {request} defines the Zyte API {parameter} parameter, "
            f"overriding Request.headers. Use Request.headers instead."
        )
        return
    if not request.headers:
        return
    for k, v in request.headers.items():
        if not v:
            continue
        decoded_v = b",".join(v).decode()
        lowercase_k = k.strip().lower()
        yield k, lowercase_k, decoded_v


def _map_custom_http_request_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    unsupported_headers: Set[str],
):
    headers = []
    for k, lowercase_k, decoded_v in _iter_headers(
        api_params=api_params,
        request=request,
        parameter="customHttpRequestHeaders",
    ):
        if lowercase_k in unsupported_headers:
            if lowercase_k != b"user-agent" or decoded_v != DEFAULT_USER_AGENT:
                logger.warning(
                    f"Request {request} defines header {k}, which "
                    f"cannot be mapped into the Zyte API "
                    f"customHttpRequestHeaders parameter."
                )
            continue
        headers.append({"name": k.decode(), "value": decoded_v})
    if headers:
        api_params["customHttpRequestHeaders"] = headers


def _map_request_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    browser_headers: Dict[str, str],
):
    request_headers = {}
    for k, lowercase_k, decoded_v in _iter_headers(
        api_params=api_params,
        request=request,
        parameter="requestHeaders",
    ):
        key = browser_headers.get(lowercase_k)
        if key is not None:
            request_headers[key] = decoded_v
        elif not (
            (
                lowercase_k == b"accept"
                and decoded_v == DEFAULT_REQUEST_HEADERS["Accept"]
            )
            or (
                lowercase_k == b"accept-language"
                and decoded_v == DEFAULT_REQUEST_HEADERS["Accept-Language"]
            )
            or (lowercase_k == b"user-agent" and decoded_v == DEFAULT_USER_AGENT)
        ):
            logger.warning(
                f"Request {request} defines header {k}, which "
                f"cannot be mapped into the Zyte API requestHeaders "
                f"parameter."
            )
    if request_headers:
        api_params["requestHeaders"] = request_headers


def _set_request_headers_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
    unsupported_headers: Set[str],
    browser_headers: Dict[str, str],
):
    """Updates *api_params*, in place, based on *request*."""
    response_body = api_params.get("httpResponseBody")
    if response_body:
        _map_custom_http_request_headers(
            api_params=api_params,
            request=request,
            unsupported_headers=unsupported_headers,
        )
    if not response_body or any(
        api_params.get(k) for k in ("browserHtml", "screenshot")
    ):
        _map_request_headers(
            api_params=api_params,
            request=request,
            browser_headers=browser_headers,
        )


def _set_http_response_body_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
):
    if not any(
        api_params.get(k) for k in ("httpResponseBody", "browserHtml", "screenshot")
    ):
        api_params.setdefault("httpResponseBody", True)
    elif api_params.get("httpResponseBody") is True and not any(
        api_params.get(k) for k in ("browserHtml", "screenshot")
    ):
        logger.warning(
            "You do not need to set httpResponseBody to True if neither "
            "browserHtml nor screenshot are set to True."
        )
    elif api_params.get("httpResponseBody") is False:
        logging.warning(
            f"Request {request} unnecessarily defines the Zyte API "
            f"'httpResponseBody' parameter with its default value, False. "
            f"It will not be sent to the server."
        )
    if api_params.get("httpResponseBody") is False:
        api_params.pop("httpResponseBody")


def _set_http_response_headers_from_request(
    *,
    api_params: Dict[str, Any],
    default_params: Dict[str, Any],
    meta_params: Dict[str, Any],
    request: Request,
):
    if any(api_params.get(k) for k in ("httpResponseBody", "browserHtml")):
        if api_params.get("httpResponseHeaders") is True and not (
            default_params.get("httpResponseHeaders") is True
            and "httpResponseHeaders" not in meta_params
        ):
            logger.error(default_params)
            logger.warning(
                "You do not need to set httpResponseHeaders to True if "
                "you set httpResponseBody or browserHtml to True. Note "
                "that httpResponseBody is set to True automatically if "
                "neither browserHtml nor screenshot are set to True."
            )
        api_params.setdefault("httpResponseHeaders", True)
    elif (
        api_params.get("httpResponseHeaders") is False
        and not default_params.get("httpResponseHeaders") is False
    ):
        logger.warning(
            "You do not need to set httpResponseHeaders to False if "
            "you do set httpResponseBody or browserHtml to True. Note "
            "that httpResponseBody is set to True automatically if "
            "neither browserHtml nor screenshot are set to True."
        )
    if api_params.get("httpResponseHeaders") is False:
        api_params.pop("httpResponseHeaders")


def _set_http_request_method_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
):
    method = api_params.get("httpRequestMethod")
    if method:
        logger.warning(
            f"Request {request} uses the Zyte API httpRequestMethod "
            f"parameter, overriding Request.method. Use Request.method "
            f"instead."
        )
        if method != request.method:
            logger.warning(
                f"The HTTP method of request {request} ({request.method}) "
                f"does not match the Zyte API httpRequestMethod parameter "
                f"({method})."
            )
    elif request.method != "GET":
        if api_params.get("httpResponseBody"):
            api_params["httpRequestMethod"] = request.method
        else:
            logger.warning(
                f"The HTTP method of request {request} ({request.method}) "
                f"is being ignored. The httpRequestMethod parameter of "
                f"Zyte API can only be set when the httpResponseBody "
                f"parameter is True."
            )


def _set_http_request_body_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
):
    body = api_params.get("httpRequestBody")
    if body:
        logger.warning(
            f"Request {request} uses the Zyte API httpRequestBody parameter, "
            f"overriding Request.body. Use Request.body instead."
        )
        decoded_body = b64decode(body)
        if decoded_body != request.body:
            logger.warning(
                f"The body of request {request} ({request.body!r}) "
                f"does not match the Zyte API httpRequestBody parameter "
                f"({body!r}; decoded: {decoded_body!r})."
            )
    elif request.body != b"":
        if api_params.get("httpResponseBody"):
            base64_body = b64encode(request.body).decode()
            api_params["httpRequestBody"] = base64_body
        else:
            logger.warning(
                f"The body of request {request} ({request.body!r}) "
                f"is being ignored. The httpRequestBody parameter of "
                f"Zyte API can only be set when the httpResponseBody "
                f"parameter is True."
            )


def _unset_unneeded_api_params(
    *,
    api_params: Dict[str, Any],
    default_params: Dict[str, Any],
    request: Request,
):
    for param, default_value in _DEFAULT_API_PARAMS.items():
        if api_params.get(param) != default_value:
            continue
        if param not in default_params or default_params.get(param) == default_value:
            logging.warning(
                f"Request {request} unnecessarily defines the Zyte API {param!r} "
                f"parameter with its default value, {default_value!r}. It will "
                f"not be sent to the server."
            )
        api_params.pop(param)


def _update_api_params_from_request(
    api_params: Dict[str, Any],
    request: Request,
    *,
    default_params: Dict[str, Any],
    meta_params: Dict[str, Any],
    unsupported_headers: Set[str],
    browser_headers: Dict[str, str],
):
    _set_http_response_body_from_request(api_params=api_params, request=request)
    _set_http_response_headers_from_request(
        api_params=api_params,
        request=request,
        default_params=default_params,
        meta_params=meta_params,
    )
    _set_http_request_method_from_request(api_params=api_params, request=request)
    _set_request_headers_from_request(
        api_params=api_params,
        request=request,
        unsupported_headers=unsupported_headers,
        browser_headers=browser_headers,
    )
    _set_http_request_body_from_request(api_params=api_params, request=request)
    _unset_unneeded_api_params(
        api_params=api_params, request=request, default_params=default_params
    )
    return api_params


def _get_raw_params(
    request: Request,
    *,
    default_params: Dict[str, Any],
):
    meta_params = request.meta.get("zyte_api", False)
    if meta_params is False:
        return None

    if not meta_params and meta_params != {}:
        warn(
            f"Setting the zyte_api request metadata key to "
            f"{meta_params!r} is deprecated. Use False instead.",
            DeprecationWarning,
        )
        return None

    if meta_params is True:
        meta_params = {}
    elif not isinstance(meta_params, Mapping):
        raise ValueError(
            f"'zyte_api' parameters in the request meta should be provided as "
            f"a dictionary, got {type(meta_params)} instead in {request}."
        )
    else:
        meta_params = copy(meta_params)

    params = copy(default_params)
    for k in list(meta_params):
        if meta_params[k] is not None:
            continue
        meta_params.pop(k)
        if k in params:
            params.pop(k)
        else:
            logger.warning(
                f"In request {request} 'zyte_api' parameter {k} is None, "
                f"which is a value reserved to unset parameters defined in "
                f"the ZYTE_API_DEFAULT_PARAMS setting, but the setting does "
                f"not define such a parameter."
            )
    params.update(meta_params)

    return params


def _get_automap_params(
    request: Request,
    *,
    default_enabled: bool,
    default_params: Dict[str, Any],
    unsupported_headers: Set[str],
    browser_headers: Dict[str, str],
):
    meta_params = request.meta.get("zyte_api_automap", default_enabled)
    if meta_params is False:
        return None

    if meta_params is True:
        meta_params = {}
    elif not isinstance(meta_params, Mapping):
        raise ValueError(
            f"'zyte_api_automap' parameters in the request meta should be "
            f"provided as a dictionary, got {type(meta_params)} instead in "
            f"{request}."
        )
    else:
        meta_params = copy(meta_params)
    original_meta_params = copy(meta_params)

    params = copy(default_params)

    for k in list(meta_params):
        if meta_params[k] is not None:
            continue
        meta_params.pop(k)
        if k in params:
            params.pop(k)
        else:
            logger.warning(
                f"In request {request} 'zyte_api_automap' parameter {k} is "
                f"None, which is a value reserved to unset parameters defined "
                f"in the ZYTE_API_AUTOMAP_PARAMS setting, but the setting "
                f"does not define such a parameter."
            )
    params.update(meta_params)

    _update_api_params_from_request(
        params,
        request,
        default_params=default_params,
        meta_params=original_meta_params,
        unsupported_headers=unsupported_headers,
        browser_headers=browser_headers,
    )

    return params


def _get_api_params(
    request: Request,
    *,
    default_params: Dict[str, Any],
    transparent_mode: bool,
    automap_params: Dict[str, Any],
    unsupported_headers: Set[str],
    browser_headers: Dict[str, str],
    job_id: Optional[str],
) -> Optional[dict]:
    """Returns a dictionary of API parameters that must be sent to Zyte API for
    the specified request, or None if the request should not be sent through
    Zyte API."""
    api_params = _get_raw_params(request, default_params=default_params)
    if api_params is None:
        api_params = _get_automap_params(
            request,
            default_enabled=transparent_mode,
            default_params=automap_params,
            unsupported_headers=unsupported_headers,
            browser_headers=browser_headers,
        )
    elif request.meta.get("zyte_api_automap", False) is not False:
        raise ValueError(
            f"Request {request} combines manually-defined parameters and "
            f"automatically-mapped parameters."
        )
    if api_params is None:
        return None

    if job_id is not None:
        api_params["jobId"] = job_id

    return api_params


def _load_default_params(settings, setting):
    params = settings.getdict(setting)
    for param in list(params):
        if params[param] is not None:
            continue
        logger.warning(
            f"Parameter {param!r} in the {setting} setting is None. Default "
            f"parameters should never be None."
        )
        params.pop(param)
    return params


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
        self._stats = crawler.stats
        self._job_id = crawler.settings.get("JOB")
        self._default_params = _load_default_params(settings, "ZYTE_API_DEFAULT_PARAMS")
        self._automap_params = _load_default_params(settings, "ZYTE_API_AUTOMAP_PARAMS")
        self._session = create_session(connection_pool_size=self._client.n_conn)
        self._retry_policy = settings.get("ZYTE_API_RETRY_POLICY")
        if self._retry_policy:
            self._retry_policy = load_object(self._retry_policy)
        self._transparent_mode = settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
        self._unsupported_headers = {
            header.strip().lower().encode()
            for header in settings.getlist(
                "ZYTE_API_UNSUPPORTED_HEADERS",
                ["Cookie", "User-Agent"],
            )
        }
        browser_headers = settings.getdict(
            "ZYTE_API_BROWSER_HEADERS",
            {"Referer": "referer"},
        )
        self._browser_headers = {
            k.strip().lower().encode(): v for k, v in browser_headers.items()
        }

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        api_params = _get_api_params(
            request,
            default_params=self._default_params,
            transparent_mode=self._transparent_mode,
            automap_params=self._automap_params,
            unsupported_headers=self._unsupported_headers,
            browser_headers=self._browser_headers,
            job_id=self._job_id,
        )
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
        api_data = {**{"url": request.url}, **api_params}
        retrying = request.meta.get("zyte_api_retry_policy")
        if retrying:
            retrying = load_object(retrying)
        else:
            retrying = self._retry_policy
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
