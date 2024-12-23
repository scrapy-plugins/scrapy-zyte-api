from base64 import b64decode, b64encode
from copy import copy
from logging import getLogger
from os import environ
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union
from warnings import warn

from scrapy import Request
from scrapy.downloadermiddlewares.httpcompression import (
    ACCEPTED_ENCODINGS,
    HttpCompressionMiddleware,
)
from scrapy.http.cookies import CookieJar
from scrapy.settings.default_settings import USER_AGENT

from ._cookies import _get_all_cookies

logger = getLogger(__name__)

_NoDefault = object()

# Map of all known root Zyte API request params and how they need to be
# handled. Sorted by appearance in
# https://docs.zyte.com/zyte-api/usage/reference.html.
_REQUEST_PARAMS: Dict[str, Dict[str, Any]] = {
    "url": {
        "default": _NoDefault,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "requestHeaders": {
        "default": {},
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,
    },
    "httpRequestMethod": {
        "default": "GET",
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "httpRequestBody": {
        "default": "",
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "httpRequestText": {
        "default": "",
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "customHttpRequestHeaders": {
        "default": [],
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,
    },
    "httpResponseBody": {
        "default": False,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "httpResponseHeaders": {
        "default": False,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "browserHtml": {
        "default": False,
        "is_extract_type": False,
        "requires_browser_rendering": True,
        "changes_fingerprint": True,
    },
    "screenshot": {
        "default": False,
        "is_extract_type": False,
        "requires_browser_rendering": True,
        "changes_fingerprint": True,
    },
    "screenshotOptions": {
        "default": {},
        "is_extract_type": False,
        "requires_browser_rendering": False,  # Not on its own.
        "changes_fingerprint": True,
    },
    "article": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "articleOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "articleList": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "articleListOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "articleNavigation": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "articleNavigationOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "jobPosting": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "jobPostingOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "product": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "productOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "productList": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "productListOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "productNavigation": {
        "default": False,
        "is_extract_type": True,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "productNavigationOptions": {
        "default": {},
        "is_extract_type": False,  # Not on its own.
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "geolocation": {
        "default": None,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "javascript": {
        "default": None,
        "is_extract_type": False,
        "requires_browser_rendering": False,  # Not on its own.
        "changes_fingerprint": True,
    },
    "actions": {
        "default": [],
        "is_extract_type": False,
        "requires_browser_rendering": False,  # Not on its own.
        "changes_fingerprint": True,
    },
    "jobId": {
        "default": None,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,
    },
    "echoData": {
        "default": None,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "viewport": {
        "default": {},
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "sessionContext": {
        "default": [],
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,  # Treated like headers.
    },
    "sessionContextParameters": {
        "default": {},
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,  # Treated like sessionContext.
    },
    "device": {
        "default": "auto",
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,  # Treated like viewport.
    },
    "cookieManagement": {
        "default": "auto",
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,  # Treated like headers.
    },
    "requestCookies": {
        "default": [],
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,  # Treated like headers.
    },
    "responseCookies": {
        "default": False,
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": True,
    },
    "experimental": {
        "default": {},
        "is_extract_type": False,
        "requires_browser_rendering": False,
        "changes_fingerprint": False,
    },
}

_BROWSER_KEYS = {
    key for key, value in _REQUEST_PARAMS.items() if value["requires_browser_rendering"]
}
_EXTRACT_KEYS = {
    key for key, value in _REQUEST_PARAMS.items() if value["is_extract_type"]
}
_BROWSER_OR_EXTRACT_KEYS = _BROWSER_KEYS | _EXTRACT_KEYS
_DEFAULT_API_PARAMS = {
    key: value["default"]
    for key, value in _REQUEST_PARAMS.items()
    if value["default"] != _NoDefault
}

ANY_VALUE = object()
ANY_VALUE_T = Any
SKIP_HEADER_T = Dict[bytes, Union[ANY_VALUE_T, str]]


def _uses_browser(api_params: Dict[str, Any]) -> bool:
    for key in _BROWSER_KEYS:
        if api_params.get(key, _REQUEST_PARAMS[key]["default"]):
            return True
    for key in _EXTRACT_KEYS:
        options = api_params.get(f"{key}Options", {})
        extract_from = options.get("extractFrom", None)
        if extract_from == "browserHtml":
            return True
    # Note: This could be a “maybe”, e.g. if no extractFrom is specified, a
    # extract key could be triggering browser rendering.
    return False


def _iter_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    header_parameter: str,
) -> Iterable[Tuple[bytes, bytes, bytes]]:
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
        decoded_k = k.decode()
        lowercase_k = k.strip().lower()
        joined_v = b",".join(v)
        decoded_v = joined_v.decode()

        if lowercase_k.startswith(b"x-crawlera-"):
            for spm_header_suffix, zapi_request_param in (
                (b"region", "geolocation"),
                (b"jobid", "jobId"),
            ):
                if lowercase_k == b"x-crawlera-" + spm_header_suffix:
                    if zapi_request_param in api_params:
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}, has "
                            f"already been defined on the request."
                        )
                    else:
                        api_params[zapi_request_param] = decoded_v
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"has been assigned to the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}."
                        )
                    break
            else:
                if lowercase_k == b"x-crawlera-profile":
                    zapi_request_param = "device"
                    if header_parameter == "requestHeaders":
                        # Browser request, no support for the device param.
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers."
                        )
                    elif zapi_request_param in api_params:
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}, has "
                            f"already been defined on the request."
                        )
                    elif decoded_v in ("desktop", "mobile"):
                        api_params[zapi_request_param] = decoded_v
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"has been assigned to the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}."
                        )
                    else:
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"cannot be mapped to the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}."
                        )
                elif lowercase_k == b"x-crawlera-cookies":
                    zapi_request_param = "cookieManagement"
                    if zapi_request_param in api_params:
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}, has "
                            f"already been defined on the request."
                        )
                    elif decoded_v == "discard":
                        api_params[zapi_request_param] = decoded_v
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"has been assigned to the matching Zyte API "
                            f"request parameter, {zapi_request_param!r}."
                        )
                    elif decoded_v == "enable":
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"does not require mapping to a Zyte API request "
                            f"parameter. To achieve the same behavior with "
                            f"Zyte API, do not set request cookies. You can "
                            f"disable cookies setting the COOKIES_ENABLED "
                            f"setting to False or setting the "
                            f"dont_merge_cookies Request.meta key to True."
                        )
                    elif decoded_v == "disable":
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"does not require mapping to a Zyte API request "
                            f"parameter, because it is the default behavior "
                            f"of Zyte API."
                        )
                    else:
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support Zyte Smart Proxy "
                            f"Manager headers, and its value ({decoded_v!r}) "
                            f"cannot be mapped to a Zyte API request "
                            f"parameter."
                        )
                else:
                    logger.warning(
                        f"Request {request} defines header {decoded_k}. This "
                        f"header has been dropped, the HTTP API of Zyte API "
                        f"does not support Zyte Smart Proxy Manager headers."
                    )
            continue

        yield k, lowercase_k, joined_v


def _map_custom_http_request_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    skip_headers: SKIP_HEADER_T,
):
    headers = []
    for k, lowercase_k, v in _iter_headers(
        api_params=api_params,
        request=request,
        header_parameter="customHttpRequestHeaders",
    ):
        if skip_headers.get(lowercase_k) in (ANY_VALUE, v):
            continue
        headers.append({"name": k.decode(), "value": v.decode()})
    if headers:
        api_params["customHttpRequestHeaders"] = headers


def _map_request_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    browser_headers: Dict[bytes, str],
    browser_ignore_headers: SKIP_HEADER_T,
):
    request_headers = {}
    for k, lowercase_k, v in _iter_headers(
        api_params=api_params,
        request=request,
        header_parameter="requestHeaders",
    ):
        key = browser_headers.get(lowercase_k)
        if key is not None:
            request_headers[key] = v.decode()
        elif lowercase_k not in browser_ignore_headers or browser_ignore_headers[
            lowercase_k
        ] not in (ANY_VALUE, v):
            logger.warning(
                f"Request {request} defines header {k.decode()}, which "
                f"cannot be mapped into the Zyte API requestHeaders "
                f"parameter. See the ZYTE_API_BROWSER_HEADERS setting."
            )
    if request_headers:
        api_params["requestHeaders"] = request_headers


def _get_extract_froms(api_params: Dict[str, Any]) -> Set[str]:
    result = set()
    for key in _EXTRACT_KEYS:
        if not api_params.get(key, False):
            continue
        options = api_params.get(f"{key}Options", {})
        result.add(options.get("extractFrom", "browserHtml"))
    return result


def _set_request_headers_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
    skip_headers: SKIP_HEADER_T,
    browser_headers: Dict[bytes, str],
    browser_ignore_headers: SKIP_HEADER_T,
):
    """Updates *api_params*, in place, based on *request*."""
    custom_http_request_headers = api_params.get("customHttpRequestHeaders")
    request_headers = api_params.get("requestHeaders")
    response_body = api_params.get("httpResponseBody")
    extract_froms = _get_extract_froms(api_params)

    if (
        (response_body or "httpResponseBody" in extract_froms)
        and custom_http_request_headers is not False
    ) or custom_http_request_headers is True:
        _map_custom_http_request_headers(
            api_params=api_params,
            request=request,
            skip_headers=skip_headers,
        )
    elif custom_http_request_headers is False:
        api_params.pop("customHttpRequestHeaders")

    if (
        request_headers is not False
        and (
            (not response_body and "httpResponseBody" not in extract_froms)
            or any(api_params.get(k) for k in _BROWSER_KEYS)
            or "browserHtml" in extract_froms
        )
    ) or request_headers is True:
        _map_request_headers(
            api_params=api_params,
            request=request,
            browser_headers=browser_headers,
            browser_ignore_headers=browser_ignore_headers,
        )
    elif request_headers is False:
        api_params.pop("requestHeaders")


def _set_http_response_body_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
):
    if not any(api_params.get(k) for k in _BROWSER_OR_EXTRACT_KEYS):
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


def _set_http_response_cookies_from_request(
    *,
    api_params: Dict[str, Any],
):
    api_params.setdefault("experimental", {})
    api_params["experimental"].setdefault("responseCookies", True)
    if api_params["experimental"]["responseCookies"] is False:
        del api_params["experimental"]["responseCookies"]


def _set_http_request_cookies_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
    cookie_jars: Dict[Any, CookieJar],
    max_cookies: int,
):
    api_params.setdefault("experimental", {})
    if "requestCookies" in api_params["experimental"]:
        request_cookies = api_params["experimental"]["requestCookies"]
        if request_cookies is False:
            del api_params["experimental"]["requestCookies"]
        elif not request_cookies and isinstance(request_cookies, list):
            logger.warning(
                (
                    "Request %(request)r is overriding automatic request "
                    "cookie mapping by explicitly setting "
                    "experimental.requestCookies to []. If this was your "
                    "intention, please use False instead of []. Otherwise, "
                    "stop defining experimental.requestCookies in your "
                    "request to let automatic mapping work."
                ),
                {
                    "request": request,
                },
            )
        return
    output_cookies = []
    input_cookies = _get_all_cookies(request, cookie_jars)
    input_cookie_count = len(input_cookies)
    if input_cookie_count > max_cookies:
        logger.warning(
            (
                "Request %(request)r would get %(count)r cookies, but request "
                "cookie automatic mapping is limited to %(max)r cookies "
                "(see the ZYTE_API_MAX_COOKIES setting), so only %(max)r "
                "cookies have been added to this request. To silence this "
                "warning, set the request cookies manually through the "
                "experimental.requestCookies Zyte API parameter instead. "
                "Alternatively, if Zyte API starts supporting more than "
                "%(max)r request cookies, update the ZYTE_API_MAX_COOKIES "
                "setting accordingly."
            ),
            {
                "request": request,
                "count": input_cookie_count,
                "max": max_cookies,
            },
        )
        input_cookies = input_cookies[:max_cookies]
    for input_cookie in input_cookies:
        output_cookie = {
            "name": input_cookie.name,
            "value": input_cookie.value,
            "domain": input_cookie.domain,
        }
        if input_cookie.path_specified:
            output_cookie["path"] = input_cookie.path
        output_cookies.append(output_cookie)
    if output_cookies:
        api_params["experimental"]["requestCookies"] = output_cookies


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


_Undefined = object()


def _unset_unneeded_api_params(
    *,
    api_params: Dict[str, Any],
    default_params: Dict[str, Any],
    request: Request,
):
    for param, default_value in _DEFAULT_API_PARAMS.items():
        value = api_params.get(param, _Undefined)
        if value is _Undefined:
            continue
        if value != default_value:
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
    skip_headers: SKIP_HEADER_T,
    browser_headers: Dict[bytes, str],
    browser_ignore_headers: SKIP_HEADER_T,
    cookies_enabled: bool,
    cookie_jars: Optional[Dict[Any, CookieJar]],
    max_cookies: int,
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
        browser_ignore_headers=browser_ignore_headers,
    )
    _set_http_request_body_from_request(api_params=api_params, request=request)
    if cookies_enabled:
        assert cookie_jars is not None  # typing
        _set_http_response_cookies_from_request(api_params=api_params)
        _set_http_request_cookies_from_request(
            api_params=api_params,
            request=request,
            cookie_jars=cookie_jars,
            max_cookies=max_cookies,
        )
        if not api_params["experimental"]:
            del api_params["experimental"]
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
    context: Optional[List[str]] = None,
):
    params = copy(default_params)
    meta_params = copy(meta_params)
    context = context or []
    for k in list(meta_params):
        if isinstance(meta_params[k], dict):
            meta_params[k] = _merge_params(
                default_params=params.get(k, {}),
                meta_params=meta_params[k],
                param=param,
                setting=setting,
                request=request,
                context=context + [k],
            )
        if meta_params[k] not in (None, {}):
            continue
        meta_params.pop(k)
        if k in params:
            params.pop(k)
        else:
            qual_param = ".".join(context + [k])
            logger.warning(
                f"In request {request} {param!r} parameter {qual_param} is "
                f"None, which is a value reserved to unset parameters defined "
                f"in the {setting} setting, but the setting does not define "
                f"such a parameter."
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
    skip_headers: SKIP_HEADER_T,
    browser_headers: Dict[bytes, str],
    browser_ignore_headers: SKIP_HEADER_T,
    cookies_enabled: bool,
    cookie_jars: Optional[Dict[Any, CookieJar]],
    max_cookies: int,
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
        browser_ignore_headers=browser_ignore_headers,
        cookies_enabled=cookies_enabled,
        cookie_jars=cookie_jars,
        max_cookies=max_cookies,
    )

    return params


def _get_api_params(
    request: Request,
    *,
    default_params: Dict[str, Any],
    transparent_mode: bool,
    automap_params: Dict[str, Any],
    skip_headers: SKIP_HEADER_T,
    browser_headers: Dict[bytes, str],
    browser_ignore_headers: SKIP_HEADER_T,
    job_id: Optional[str],
    cookies_enabled: bool,
    cookie_jars: Optional[Dict[Any, CookieJar]],
    max_cookies: int,
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
            browser_ignore_headers=browser_ignore_headers,
            cookies_enabled=cookies_enabled,
            cookie_jars=cookie_jars,
            max_cookies=max_cookies,
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
        if params[param] not in (None, {}):
            continue
        logger.warning(
            f"Parameter {param!r} in the {setting} setting is "
            f"{params[param]!r}. Default parameters should never be "
            f"{params[param]!r}."
        )
        params.pop(param)
    return params


def _load_http_skip_headers(settings):
    return {
        header.strip().lower().encode(): ANY_VALUE
        for header in settings.getlist(
            "ZYTE_API_SKIP_HEADERS",
            ["Cookie"],
        )
    }


def _load_mw_skip_headers(crawler):
    mw_skip_headers = {}

    accept_encoding_in_default_headers = False
    user_agent_in_default_headers = False
    if not crawler.settings.getpriority("DEFAULT_REQUEST_HEADERS"):
        for name, value in crawler.settings["DEFAULT_REQUEST_HEADERS"].items():
            mw_skip_headers[name.lower().encode()] = value.encode()
    else:
        for header in crawler.settings["DEFAULT_REQUEST_HEADERS"]:
            lowercase_k = header.lower().encode()
            if lowercase_k == b"accept-encoding":
                accept_encoding_in_default_headers = True
            if lowercase_k == b"user-agent":
                user_agent_in_default_headers = True

    if not accept_encoding_in_default_headers:
        engine = getattr(crawler, "engine", None)
        if engine:
            for mw in engine.downloader.middleware.middlewares:
                if isinstance(mw, HttpCompressionMiddleware):
                    mw_skip_headers[b"accept-encoding"] = b", ".join(ACCEPTED_ENCODINGS)
        else:
            # Assume the default scenario on tests that do not initialize the engine.
            mw_skip_headers[b"accept-encoding"] = b", ".join(ACCEPTED_ENCODINGS)

    if not user_agent_in_default_headers and not crawler.settings.getpriority(
        "USER_AGENT"
    ):
        mw_skip_headers[b"user-agent"] = USER_AGENT.encode()

    return mw_skip_headers


def _load_browser_headers(settings) -> Dict[bytes, str]:
    browser_headers = settings.getdict(
        "ZYTE_API_BROWSER_HEADERS",
        {"Referer": "referer"},
    )
    return {k.strip().lower().encode(): v for k, v in browser_headers.items()}


class _ParamParser:
    def __init__(self, crawler, cookies_enabled=None):
        settings = crawler.settings
        self._automap_params = _load_default_params(settings, "ZYTE_API_AUTOMAP_PARAMS")
        self._browser_headers = _load_browser_headers(settings)
        self._default_params = _load_default_params(settings, "ZYTE_API_DEFAULT_PARAMS")
        self._job_id = environ.get("SHUB_JOBKEY", None)
        self._transparent_mode = settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
        self._http_skip_headers = _load_http_skip_headers(settings)
        self._mw_skip_headers = _load_mw_skip_headers(crawler)
        self._warn_on_cookies = False
        if cookies_enabled is not None:
            self._cookies_enabled = cookies_enabled
        elif settings.getbool("ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED") is True:
            self._cookies_enabled = settings.getbool("COOKIES_ENABLED")
            if not self._cookies_enabled:
                logger.warning(
                    "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED is True, but it "
                    "will have no effect because COOKIES_ENABLED is False."
                )
        else:
            self._cookies_enabled = False
            self._warn_on_cookies = settings.getbool("COOKIES_ENABLED")
        self._max_cookies = settings.getint("ZYTE_API_MAX_COOKIES", 100)
        self._crawler = crawler
        self._cookie_jars = None

    def _request_skip_headers(self, request):
        result = dict(self._mw_skip_headers)
        for name in request.meta.get("_pre_mw_headers", set()):
            if name in result:
                del result[name]
        return result

    def parse(self, request):
        dont_merge_cookies = request.meta.get("dont_merge_cookies", False)
        use_default_params = request.meta.get("zyte_api_default_params", True)
        cookies_enabled = self._cookies_enabled and not dont_merge_cookies
        request_skip_headers = self._request_skip_headers(request)
        params = _get_api_params(
            request,
            default_params=self._default_params if use_default_params else {},
            transparent_mode=self._transparent_mode,
            automap_params=self._automap_params,
            skip_headers={**request_skip_headers, **self._http_skip_headers},
            browser_headers=self._browser_headers,
            browser_ignore_headers={b"cookie": ANY_VALUE, **request_skip_headers},
            job_id=self._job_id,
            cookies_enabled=cookies_enabled,
            cookie_jars=self._cookie_jars,
            max_cookies=self._max_cookies,
        )
        if not dont_merge_cookies and self._warn_on_cookies:
            self._handle_warn_on_cookies(request, params)
        return params

    def _handle_warn_on_cookies(self, request, params):
        if params and params.get("experimental", {}).get("requestCookies") is not None:
            return
        if self._cookie_jars is None:
            return
        input_cookies = _get_all_cookies(request, self._cookie_jars)
        if len(input_cookies) <= 0:
            return
        logger.warning(
            (
                "Cookies are enabled for request %(request)r, and there are "
                "cookies in the cookiejar, but "
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED is False, so automatic "
                "mapping will not map cookies for this or any other request. "
                "To silence this warning, disable cookies for all requests "
                "that use automatic mapping, either with the "
                "COOKIES_ENABLED setting or with the dont_merge_cookies "
                "request metadata key."
            ),
            {
                "request": request,
            },
        )
        self._warn_on_cookies = False
