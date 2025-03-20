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
from scrapy.utils.python import to_bytes, to_unicode

from ._cookies import _get_all_cookies

logger = getLogger(__name__)

_NoDefault = object()

# Map of all known root Zyte API request params and how they need to be
# handled. Sorted by appearance in
# https://docs.zyte.com/zyte-api/usage/reference.html.
#
# *default* indicates the default value of a given parameter. It is used by
# automatic parameter mapping to not send parameters with their default value
# to the server, and warn when they are unnecessarily defined by users with
# those values (it could still be necessary to override a non-default value set
# by a lower-priority setting).
#
# *is_extract_type* (default: False) indicates that the given request field is
# an extract output field, with the following effects:
#
# -   httpResponseBody and httpResponseHeaders are not enabled by default if an
#     extract type field is enabled.
#
# -   The extractFrom key of <type>Options is taken into account for the
#     following:
#
#     -   If there is certainty that browser rendering is not used, the
#         fragment part of the url field is ignored during request
#         fingerprinting.
#
#     -   If there are headers to map, httpResponseBody in any extractFrom
#         forces customHttpRequestHeaders to be used, browserHtml forces
#         requestHeaders to be used, and in the absence of both, requestHeaders
#         is used.
#
#         An exception is made for serp, which does not support header mapping.
#
#     *default_extract_from* can be used to indicate a value that can be
#     assumed for <type>Options.extractFrom if not set. It defaults to
#     _NoDefault, meaning it could be either httpResponseBody or browserHtml,
#     since for most extraction types Zyte API may use a different default per
#     domain. If browser rendering may be used, URL fragments are taken into
#     account for request fingerprinting purposes.
#
# *is_browser_output* (default: False) indicates that the given request field
# is an output that requires browser rendering. If any such output is enabled:
#
# -   httpResponseBody and httpResponseHeaders are not enabled by default.
#
# -   Header mapping with requestHeaders is used.
#
# -   URL fragments are taken into account for request fingerprinting purposes.
#
# *changes_fingerprint* (default: True) indicates that the value of the
# corresponding field must be taken into account for request fingerprinting
# purposes, i.e. 2 requests with a different value for that field but otherwise
# identical should be treated as different requests, not as duplicate requests.
#
_REQUEST_PARAMS: Dict[str, Dict[str, Any]] = {
    "url": {
        "default": _NoDefault,
    },
    "requestHeaders": {
        "default": {},
        "changes_fingerprint": False,
    },
    "tags": {
        "default": {},
    },
    "ipType": {
        "default": None,
        "changes_fingerprint": False,
    },
    "httpRequestMethod": {
        "default": "GET",
    },
    "httpRequestBody": {
        "default": "",
    },
    "httpRequestText": {
        "default": "",
    },
    "customHttpRequestHeaders": {
        "default": [],
        "changes_fingerprint": False,
    },
    "httpResponseBody": {
        "default": False,
    },
    "httpResponseHeaders": {
        "default": False,
    },
    "browserHtml": {
        "default": False,
        "is_browser_output": True,
    },
    "screenshot": {
        "default": False,
        "is_browser_output": True,
    },
    "screenshotOptions": {
        "default": {},
    },
    "article": {
        "default": False,
        "is_extract_type": True,
    },
    "articleOptions": {
        "default": {},
    },
    "articleList": {
        "default": False,
        "is_extract_type": True,
    },
    "articleListOptions": {
        "default": {},
    },
    "articleNavigation": {
        "default": False,
        "is_extract_type": True,
    },
    "articleNavigationOptions": {
        "default": {},
    },
    "forumThread": {
        "default": False,
        "is_extract_type": True,
    },
    "forumThreadOptions": {
        "default": {},
    },
    "jobPosting": {
        "default": False,
        "is_extract_type": True,
    },
    "jobPostingOptions": {
        "default": {},
    },
    "jobPostingNavigation": {
        "default": False,
        "is_extract_type": True,
    },
    "jobPostingNavigationOptions": {
        "default": {},
    },
    "product": {
        "default": False,
        "is_extract_type": True,
    },
    "productOptions": {
        "default": {},
    },
    "productList": {
        "default": False,
        "is_extract_type": True,
    },
    "productListOptions": {
        "default": {},
    },
    "productNavigation": {
        "default": False,
        "is_extract_type": True,
    },
    "productNavigationOptions": {
        "default": {},
    },
    # NOTE: is_extract_type is not set to True here because, for everything
    # that matters when it comes to automatic parameter mapping and request
    # fingerprinting, this parameter is not like the other extraction
    # parameters, e.g. it can (in fact, has to) be combined with other
    # extraction parameters, and has no extractFrom option.
    "customAttributes": {
        "default": None,
    },
    "customAttributesOptions": {
        "default": {},
    },
    "geolocation": {
        "default": None,
    },
    "javascript": {
        "default": None,
    },
    "actions": {
        "default": [],
    },
    "jobId": {
        "default": None,
        "changes_fingerprint": False,
    },
    "echoData": {
        "default": None,
    },
    "viewport": {
        "default": {},
    },
    "followRedirect": {
        "default": True,
    },
    "sessionContext": {
        "default": [],
    },
    "sessionContextParameters": {
        "default": {},
        "changes_fingerprint": False,
    },
    "session": {
        "default": {},
        "changes_fingerprint": False,
    },
    "networkCapture": {
        "default": [],
    },
    "device": {
        "default": "desktop",
    },
    "cookieManagement": {
        "default": "auto",
        "changes_fingerprint": False,
    },
    "requestCookies": {
        "default": [],
        "changes_fingerprint": False,
    },
    "responseCookies": {
        "default": False,
    },
    "serp": {
        "default": False,
        "is_extract_type": True,
        "default_extract_from": "httpResponseBody",
    },
    "serpOptions": {
        "default": {},
    },
    "experimental": {
        "default": {},
        "changes_fingerprint": False,
    },
}

_BROWSER_KEYS = {
    key
    for key, value in _REQUEST_PARAMS.items()
    if value.get("is_browser_output", False)
}
_EXTRACT_KEYS = {
    key for key, value in _REQUEST_PARAMS.items() if value.get("is_extract_type", False)
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


def _may_use_browser(api_params: Dict[str, Any]) -> bool:
    """Return ``False`` if *api_params* indicate with certainty that browser
    rendering will not be used, or ``True`` otherwise."""
    for key in _BROWSER_KEYS:
        if api_params.get(key, _DEFAULT_API_PARAMS[key]):
            return True
    extract_froms = _get_extract_froms(api_params)
    if "browserHtml" in extract_froms:
        return True
    if "httpResponseBody" in extract_froms:
        return False
    if api_params.get("httpResponseBody", _DEFAULT_API_PARAMS["httpResponseBody"]):
        return False
    return True


def session_id_to_session(session_id):
    return {"id": session_id}


def str_to_bool(value):
    return value.strip().lower() not in ("", "false")


def _is_safe_header(k, v, /, *, api_params, request):
    k = k.strip()
    lowercase_k = to_bytes(k.lower())
    if not (lowercase_k.startswith(b"zyte-") or lowercase_k.startswith(b"x-crawlera-")):
        return True

    decoded_k = to_unicode(k)
    decoded_v = to_unicode(v)

    if lowercase_k.startswith(b"zyte-"):
        for proxy_header_suffix, zapi_request_param, processor in (
            (b"browser-html", "browserHtml", str_to_bool),
            (b"cookie-management", "cookieManagement", str.strip),
            (b"device", "device", str.strip),
            (
                b"disable-follow-redirect",
                "followRedirect",
                lambda v: not str_to_bool(v),
            ),
            (b"geolocation", "geolocation", str.strip),
            (b"iptype", "ipType", str.strip),
            (b"jobid", "jobId", str.strip),
            (b"session-id", "session", session_id_to_session),
        ):
            if lowercase_k == b"zyte-" + proxy_header_suffix:
                if zapi_request_param in api_params:
                    logger.warning(
                        f"Request {request} defines header {decoded_k}. "
                        f"This header has been dropped, the HTTP API of "
                        f"Zyte API does not support proxy mode headers, "
                        f"and the matching HTTP API request parameter, "
                        f"{zapi_request_param!r}, has already been "
                        f"defined on the request "
                        f"(as {api_params[zapi_request_param]!r})."
                    )
                else:
                    processed_value = processor(decoded_v)
                    if processed_value != _DEFAULT_API_PARAMS[zapi_request_param]:
                        api_params[zapi_request_param] = processed_value
                        if decoded_v == processed_value:
                            logger.warning(
                                f"Request {request} defines header "
                                f"{decoded_k}. This header has been dropped, "
                                f"the HTTP API of Zyte API does not support "
                                f"proxy mode headers, and its value "
                                f"({decoded_v!r}) has been assigned to the "
                                f"matching HTTP API request parameter, "
                                f"{zapi_request_param!r}."
                            )
                        else:
                            logger.warning(
                                f"Request {request} defines header "
                                f"{decoded_k}. This header has been dropped, "
                                f"the HTTP API of Zyte API does not support "
                                f"proxy mode headers, and its value "
                                f"({decoded_v!r}) has been converted into "
                                f"{processed_value!r} and assigned to the "
                                f"matching HTTP API request parameter, "
                                f"{zapi_request_param!r}."
                            )
                    else:
                        logger.warning(
                            f"Request {request} defines header {decoded_k}. "
                            f"This header has been dropped, the HTTP API of "
                            f"Zyte API does not support proxy mode headers, "
                            f"and its value ({decoded_v!r}) matches the "
                            f"default value of the matching HTTP API request "
                            f"parameter, {zapi_request_param!r}."
                        )
                break
        else:
            if lowercase_k == b"zyte-client":
                logger.warning(
                    f"Request {request} defines header {decoded_k}. This "
                    f"header has been dropped, the HTTP API of Zyte API "
                    f"does not support proxy mode headers, and "
                    f"scrapy-zyte-api automatically fills the User-Agent "
                    f"header, making this proxy mode header unnecessary."
                )
            elif lowercase_k == b"zyte-override-headers":
                logger.warning(
                    f"Request {request} defines header {decoded_k}. This "
                    f"header has been dropped, the HTTP API of Zyte API "
                    f"does not support proxy mode headers, and this "
                    f"specific header is not necessary when using the "
                    f"HTTP API."
                )
            else:
                logger.warning(
                    f"Request {request} defines header {decoded_k}. This "
                    f"header has been dropped, the HTTP API of Zyte API "
                    f"does not support proxy mode headers."
                )
    else:
        assert lowercase_k.startswith(b"x-crawlera-")
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
                        f"already been defined on the request (as "
                        f"{api_params[zapi_request_param]!r})."
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
                if zapi_request_param in api_params:
                    logger.warning(
                        f"Request {request} defines header {decoded_k}. "
                        f"This header has been dropped, the HTTP API of "
                        f"Zyte API does not support Zyte Smart Proxy "
                        f"Manager headers, and the matching Zyte API "
                        f"request parameter, {zapi_request_param!r}, has "
                        f"already been defined on the request."
                    )
                elif decoded_v == "mobile":
                    api_params[zapi_request_param] = decoded_v
                    logger.warning(
                        f"Request {request} defines header {decoded_k}. "
                        f"This header has been dropped, the HTTP API of "
                        f"Zyte API does not support Zyte Smart Proxy "
                        f"Manager headers, and its value ({decoded_v!r}) "
                        f"has been assigned to the matching Zyte API "
                        f"request parameter, {zapi_request_param!r}."
                    )
                elif decoded_v == "desktop":
                    logger.warning(
                        f"Request {request} defines header {decoded_k}. "
                        f"This header has been dropped, the HTTP API of "
                        f"Zyte API does not support Zyte Smart Proxy "
                        f"Manager headers, and its value ({decoded_v!r}) "
                        f"is the default value of the matching Zyte API "
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
    return False


def _process_manual_custom_http_request_headers(
    api_params: Dict[str, Any],
    request: Request,
) -> None:
    headers = []
    for header_dict in api_params.pop("customHttpRequestHeaders"):
        if _is_safe_header(
            header_dict["name"],
            header_dict["value"],
            api_params=api_params,
            request=request,
        ):
            headers.append(header_dict)
    if headers:
        api_params["customHttpRequestHeaders"] = headers


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
        if header_parameter == "customHttpRequestHeaders":
            _process_manual_custom_http_request_headers(api_params, request)
        return
    if not request.headers:
        return
    for k, vs in request.headers.items():
        if not vs:
            continue
        v = b",".join(vs)
        if _is_safe_header(k, v, api_params=api_params, request=request):
            yield k, k.strip().lower(), v


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


def _warn_about_request_headers(
    *,
    api_params: Dict[str, Any],
    request: Request,
    skip_headers: SKIP_HEADER_T,
):
    for name, values in request.headers.items():
        if not values:
            continue
        lowercase_name = name.strip().lower()
        value = b",".join(values)
        if skip_headers.get(lowercase_name) in (ANY_VALUE, value):
            continue
        logger.warning(
            f"Request {request} enables 'serp', which cannot be combined with "
            f"request headers. However, the request also defines header "
            f"{name!r}. The header will not be mapped to any Zyte API request "
            f"field. To silence this warning, remove the header from the "
            f"request or add it to the ZYTE_API_SKIP_HEADERS setting."
        )


def _get_extract_from(api_params: Dict[str, Any], extract_type: str) -> Union[str, Any]:
    options = api_params.get(f"{extract_type}Options", {})
    default_extract_from = _REQUEST_PARAMS[extract_type].get(
        "default_extract_from", _NoDefault
    )
    return options.get("extractFrom", default_extract_from)


def _get_extract_froms(api_params: Dict[str, Any]) -> Set[str]:
    result = set()
    for key in _EXTRACT_KEYS:
        if not api_params.get(key, False):
            continue
        result.add(_get_extract_from(api_params, key))
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
    if api_params.get("serp", False):
        _warn_about_request_headers(
            api_params=api_params,
            request=request,
            skip_headers=skip_headers,
        )
        return

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


def proxy_mode_browser_html_enabled(request: Request) -> bool:
    for k, v in request.headers.items():
        if not v:
            continue
        lowercase_k = k.strip().lower()
        if lowercase_k != b"zyte-browser-html":
            continue
        joined_v = b",".join(v)
        decoded_v = joined_v.decode()
        return str_to_bool(decoded_v)
    return False


def _set_http_response_body_from_request(
    *,
    api_params: Dict[str, Any],
    request: Request,
):
    if not any(
        api_params.get(k) for k in _BROWSER_OR_EXTRACT_KEYS
    ) and not proxy_mode_browser_html_enabled(request):
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
        and default_params.get("httpResponseHeaders") is not False
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
    elif "customHttpRequestHeaders" in api_params:
        _process_manual_custom_http_request_headers(api_params, request)

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
