from base64 import b64decode, b64encode
from copy import copy
from logging import getLogger
from typing import Any, Dict, Mapping, Optional, Set
from warnings import warn

from scrapy import Request
from scrapy.settings.default_settings import DEFAULT_REQUEST_HEADERS
from scrapy.settings.default_settings import USER_AGENT as DEFAULT_USER_AGENT

logger = getLogger(__name__)

_DEFAULT_API_PARAMS = {
    "browserHtml": False,
    "screenshot": False,
}


def _iter_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    header_parameter: str,
):
    headers = api_params.get(header_parameter)
    if headers not in (None, True):
        logger.warning(
            f"Request {request} defines the Zyte API {header_parameter} "
            f"parameter, overriding Request.headers. Use Request.headers "
            f"instead."
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
    skip_headers: Set[str],
):
    headers = []
    for k, lowercase_k, decoded_v in _iter_headers(
        api_params=api_params,
        request=request,
        header_parameter="customHttpRequestHeaders",
    ):
        if lowercase_k in skip_headers:
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
        header_parameter="requestHeaders",
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
    skip_headers: Set[str],
    browser_headers: Dict[str, str],
):
    """Updates *api_params*, in place, based on *request*."""
    custom_http_request_headers = api_params.get("customHttpRequestHeaders")
    request_headers = api_params.get("requestHeaders")
    response_body = api_params.get("httpResponseBody")

    if (
        response_body
        and custom_http_request_headers is not False
        or custom_http_request_headers is True
    ):
        _map_custom_http_request_headers(
            api_params=api_params,
            request=request,
            skip_headers=skip_headers,
        )
    elif custom_http_request_headers is False:
        api_params.pop("customHttpRequestHeaders")

    if (
        (
            not response_body
            or any(api_params.get(k) for k in ("browserHtml", "screenshot"))
        )
        and request_headers is not False
        or request_headers is True
    ):
        _map_request_headers(
            api_params=api_params,
            request=request,
            browser_headers=browser_headers,
        )
    elif request_headers is False:
        api_params.pop("requestHeaders")


def _set_http_response_body_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
):
    if not any(
        api_params.get(k) for k in ("httpResponseBody", "browserHtml", "screenshot")
    ):
        api_params.setdefault("httpResponseBody", True)
    elif api_params.get("httpResponseBody") is False:
        logger.warning(
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
):
    if api_params.get("httpResponseBody"):
        api_params.setdefault("httpResponseHeaders", True)
    elif (
        api_params.get("httpResponseHeaders") is False
        and not default_params.get("httpResponseHeaders") is False
    ):
        logger.warning(
            "You do not need to set httpResponseHeaders to False if "
            "neither httpResponseBody nor browserHtml are set to True. Note "
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
        api_params["httpRequestMethod"] = request.method


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
        base64_body = b64encode(request.body).decode()
        api_params["httpRequestBody"] = base64_body


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
            logger.warning(
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
    skip_headers: Set[str],
    browser_headers: Dict[str, str],
):
    _set_http_response_body_from_request(api_params=api_params, request=request)
    _set_http_response_headers_from_request(
        api_params=api_params,
        default_params=default_params,
        meta_params=meta_params,
    )
    _set_http_request_method_from_request(api_params=api_params, request=request)
    _set_request_headers_from_request(
        api_params=api_params,
        request=request,
        skip_headers=skip_headers,
        browser_headers=browser_headers,
    )
    _set_http_request_body_from_request(api_params=api_params, request=request)
    _unset_unneeded_api_params(
        api_params=api_params, request=request, default_params=default_params
    )
    return api_params


def _copy_meta_params_as_dict(
    meta_params: Dict[str, Any],
    *,
    param: str,
    request: Request,
):
    if meta_params is True:
        return {}
    elif not isinstance(meta_params, Mapping):
        raise ValueError(
            f"'{param}' parameters in the request meta should be provided as "
            f"a dictionary, got {type(meta_params)} instead in {request}."
        )
    else:
        return copy(meta_params)


def _merge_params(
    *,
    default_params: Dict[str, Any],
    meta_params: Dict[str, Any],
    param: str,
    setting: str,
    request: Request,
):
    params = copy(default_params)
    meta_params = copy(meta_params)
    for k in list(meta_params):
        if meta_params[k] is not None:
            continue
        meta_params.pop(k)
        if k in params:
            params.pop(k)
        else:
            logger.warning(
                f"In request {request} {param!r} parameter {k} is None, "
                f"which is a value reserved to unset parameters defined in "
                f"the {setting} setting, but the setting does not define such "
                f"a parameter."
            )
    params.update(meta_params)
    return params


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

    meta_params = _copy_meta_params_as_dict(
        meta_params,
        param="zyte_api",
        request=request,
    )

    return _merge_params(
        default_params=default_params,
        meta_params=meta_params,
        param="zyte_api",
        setting="ZYTE_API_DEFAULT_PARAMS",
        request=request,
    )


def _get_automap_params(
    request: Request,
    *,
    default_enabled: bool,
    default_params: Dict[str, Any],
    skip_headers: Set[str],
    browser_headers: Dict[str, str],
):
    meta_params = request.meta.get("zyte_api_automap", default_enabled)
    if meta_params is False:
        return None

    meta_params = _copy_meta_params_as_dict(
        meta_params,
        param="zyte_api_automap",
        request=request,
    )

    params = _merge_params(
        default_params=default_params,
        meta_params=meta_params,
        param="zyte_api_automap",
        setting="ZYTE_API_AUTOMAP_PARAMS",
        request=request,
    )

    _update_api_params_from_request(
        params,
        request,
        default_params=default_params,
        meta_params=meta_params,
        skip_headers=skip_headers,
        browser_headers=browser_headers,
    )

    return params


def _get_api_params(
    request: Request,
    *,
    default_params: Dict[str, Any],
    transparent_mode: bool,
    automap_params: Dict[str, Any],
    skip_headers: Set[str],
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
            skip_headers=skip_headers,
            browser_headers=browser_headers,
        )
        if api_params is None:
            return None
    elif request.meta.get("zyte_api_automap", False) is not False:
        raise ValueError(
            f"Request {request} combines manually-defined parameters and "
            f"automatically-mapped parameters."
        )

    if job_id is not None:
        api_params["jobId"] = job_id

    api_params["url"] = request.url

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


def _load_skip_headers(settings):
    return {
        header.strip().lower().encode()
        for header in settings.getlist(
            "ZYTE_API_SKIP_HEADERS",
            ["Cookie", "User-Agent"],
        )
    }


def _load_browser_headers(settings):
    browser_headers = settings.getdict(
        "ZYTE_API_BROWSER_HEADERS",
        {"Referer": "referer"},
    )
    return {k.strip().lower().encode(): v for k, v in browser_headers.items()}


class _ParamParser:
    def __init__(self, settings):
        self._automap_params = _load_default_params(settings, "ZYTE_API_AUTOMAP_PARAMS")
        self._browser_headers = _load_browser_headers(settings)
        self._default_params = _load_default_params(settings, "ZYTE_API_DEFAULT_PARAMS")
        self._job_id = settings.get("JOB")
        self._transparent_mode = settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
        self._skip_headers = _load_skip_headers(settings)

    def parse(self, request):
        return _get_api_params(
            request,
            default_params=self._default_params,
            transparent_mode=self._transparent_mode,
            automap_params=self._automap_params,
            skip_headers=self._skip_headers,
            browser_headers=self._browser_headers,
            job_id=self._job_id,
        )
