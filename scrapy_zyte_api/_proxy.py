from __future__ import annotations

import json
import logging
from base64 import b64decode, b64encode
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from zyte_api import RequestError
from zyte_api.stats import Statistics  # type: ignore[attr-defined]

from scrapy_zyte_api._cookies import _parse_set_cookie_header
from scrapy_zyte_api._utils import str_to_bool
from scrapy_zyte_api.utils import USER_AGENT

if TYPE_CHECKING:
    from collections.abc import Callable

    from scrapy import Request
    from scrapy.http import Headers, Response

logger = logging.getLogger(__name__)

PROXY_MODE_PARAMS = {
    "url",
    "httpResponseBody",
    "httpResponseHeaders",
    "browserHtml",
    "device",
    "geolocation",
    "session",
    "jobId",
    "javascript",
    "cookieManagement",
    "ipType",
    "followRedirect",
    "requestHeaders",
    "customHttpRequestHeaders",
    "httpRequestBody",
    "httpRequestMethod",
    "tags",
    "requestCookies",
    "responseCookies",
}
_BROWSER_INCOMPATIBLE_COOKIE_PARAMS = frozenset({"requestCookies", "responseCookies"})

_PROXY_TYPE_MAP = {
    "/auth/proxy-auth-not-valid": "/auth/key-not-found",
    "/request/header-size": "/request/invalid",
}
_PROXY_STATUS_MAP = {
    407: 401,
    431: 400,
}

# Maximum total request header section size accepted by proxy mode before it
# responds with 431 /request/header-size.
_PROXY_HEADER_SECTION_LIMIT = 100 * 1024
# Per-header bytes the proxy's HTTP decoder counts on top of the name and value:
# the ": " separator and the trailing CRLF.
_PROXY_HEADER_LINE_OVERHEAD = len(b": ") + len(b"\r\n")
# Reserve for header bytes that _estimate_proxy_header_section_size does not
# model but that the proxy still counts: Proxy-Authorization, Host,
# Content-Length, Connection.
_PROXY_HEADER_SECTION_RESERVE = 512

_PROTECTED_HEADERS = {
    b"accept": "Accept",
    b"accept-encoding": "Accept-Encoding",
    b"user-agent": "User-Agent",
}


@dataclass(frozen=True)
class _ProxyHeaderParam:
    """Single source of truth tying a Zyte API proxy mode ``Zyte-*`` header to
    its matching HTTP API request parameter and the conversions between them.
    """

    header: str
    param: str
    to_header: Callable[[dict[str, Any]], str | None]
    from_header: Callable[[str], Any] | None = None

    @property
    def header_lower(self) -> bytes:
        return self.header.lower().encode()


def _session_to_header(api_params: dict[str, Any]) -> str | None:
    session = api_params.get("session")
    if isinstance(session, dict) and session.get("id"):
        return session["id"]
    return None


_PROXY_HEADER_PARAMS: tuple[_ProxyHeaderParam, ...] = (
    _ProxyHeaderParam(
        "Zyte-Browser-Html",
        "browserHtml",
        lambda p: "true" if p.get("browserHtml") else None,
        from_header=str_to_bool,
    ),
    _ProxyHeaderParam(
        "Zyte-Cookie-Management",
        "cookieManagement",
        lambda p: v if (v := p.get("cookieManagement")) and v != "auto" else None,
        from_header=str.strip,
    ),
    _ProxyHeaderParam(
        "Zyte-Device",
        "device",
        lambda p: v if (v := p.get("device")) and v != "desktop" else None,
        from_header=str.strip,
    ),
    _ProxyHeaderParam(
        "Zyte-Disable-Follow-Redirect",
        "followRedirect",
        lambda p: "true" if p.get("followRedirect") is False else None,
        from_header=lambda v: not str_to_bool(v),
    ),
    _ProxyHeaderParam(
        "Zyte-Geolocation",
        "geolocation",
        lambda p: p.get("geolocation") or None,
        from_header=str.strip,
    ),
    _ProxyHeaderParam(
        "Zyte-IPType",
        "ipType",
        lambda p: p.get("ipType") or None,
        from_header=str.strip,
    ),
    _ProxyHeaderParam(
        "Zyte-JobId",
        "jobId",
        lambda p: p.get("jobId") or None,
        from_header=str.strip,
    ),
    _ProxyHeaderParam(
        "Zyte-Session-ID",
        "session",
        _session_to_header,
        from_header=lambda value: {"id": value},
    ),
    _ProxyHeaderParam(
        "Zyte-Tags",
        "tags",
        lambda p: (
            json.dumps(p["tags"], separators=(",", ":")) if p.get("tags") else None
        ),
        from_header=json.loads,
    ),
)

_PROXY_HEADER_BY_LOWER: dict[bytes, _ProxyHeaderParam] = {
    d.header_lower: d for d in _PROXY_HEADER_PARAMS
}
_ZYTE_HEADER_TO_PARAM: dict[bytes, str] = {
    d.header_lower: d.param for d in _PROXY_HEADER_PARAMS
}

_KNOWN_PROXY_HEADERS = set(_ZYTE_HEADER_TO_PARAM) | {
    b"zyte-client",
    b"zyte-override-headers",
}

_warned_conflict_headers: set[bytes] = set()


def _get_unknown_proxy_mode_headers(request: Request) -> list[str]:
    """Return the names of the ``Zyte-*`` headers in *request* that
    scrapy-zyte-api does not recognize as proxy mode headers."""
    unknown = []
    for header in request.headers:
        lower = header.strip().lower()
        if lower.startswith(b"zyte-") and lower not in _KNOWN_PROXY_HEADERS:
            unknown.append(header.decode())
    return unknown


def _get_proxy_incompatible_params(
    params: dict[str, Any], *, browser_rendering: bool = False
) -> list[str]:
    """Return the names of the Zyte API parameters in *params* that proxy
    mode does not support.

    Set *browser_rendering* to ``True`` when the request uses browser rendering
    (``browserHtml``), so that the cookie parameters that proxy mode cannot
    represent faithfully in that case (see
    :data:`_BROWSER_INCOMPATIBLE_COOKIE_PARAMS`) are reported as incompatible.
    """

    def _incompatible(name: str) -> bool:
        return name not in PROXY_MODE_PARAMS or (
            browser_rendering and name in _BROWSER_INCOMPATIBLE_COOKIE_PARAMS
        )

    incompatible: list[str] = []
    for key, value in params.items():
        if key == "experimental":
            incompatible.extend(
                f"experimental.{subkey}"
                for subkey in value or {}
                if _incompatible(subkey)
            )
        elif key == "javascript":
            # For browser requests proxy mode always runs JavaScript and it
            # cannot be disabled; for non-browser requests the toggle is a
            # no-op. Either way, javascript: False cannot be honored.
            if value is False:
                incompatible.append("javascript")
        elif _incompatible(key):
            incompatible.append(key)
    return incompatible


def _get_raw_param_value(api_params: dict[str, Any], header_lower: bytes) -> Any:
    if header_lower == b"zyte-session-id":
        session = api_params.get("session")
        return session.get("id") if isinstance(session, dict) else None
    param = _ZYTE_HEADER_TO_PARAM.get(header_lower)
    return api_params.get(param) if param else None


def _param_is_set(api_params: dict[str, Any], header_lower: bytes) -> bool:
    """Whether the HTTP API parameter that *header_lower* maps to is present in
    *api_params*.

    Unlike checking the generated proxy headers, this detects a parameter even
    when its value matches the default and therefore produces no proxy header
    (e.g. ``device: desktop``): the parameter is still user-defined and thus
    conflicts with the matching ``Zyte-*`` header.
    """
    if header_lower == b"zyte-session-id":
        return "id" in (api_params.get("session") or {})
    return _ZYTE_HEADER_TO_PARAM[header_lower] in api_params


def _collect_proxy_headers(
    request: Request,
    api_params: dict[str, Any],
    *,
    user_agent: str | None = USER_AGENT,
    warn: bool = True,
) -> tuple[dict[str, str], str | None, bytes | None]:
    """Assemble the proxy mode request headers (plus method and body) for
    *request*, returning ``(headers, method, body)``.

    The headers start from those derived from *api_params*
    (:func:`_params_to_proxy_headers`) and are extended with the ``Zyte-*``
    control headers passed through from ``Request.headers`` and the automatic
    ``Zyte-Client`` header. This is shared by :func:`_build_proxy_request`,
    which sends the request, and :func:`_estimate_proxy_header_section_size`,
    which only measures it, so the estimate cannot drift from what is sent. Set
    *warn* to ``False`` to suppress the conflict/override warnings, leaving the
    estimation path free of side effects.
    """
    proxy_headers, proxy_method, proxy_body = _params_to_proxy_headers(api_params)

    param_lower_to_key = {k.lower(): k for k in proxy_headers}
    # Whether the request explicitly defines a Zyte-Client header, and its value
    # (empty when set to None or "", which means "do not send Zyte-Client").
    user_set_zyte_client = False
    user_zyte_client = ""
    for header_bytes in request.headers:
        lower = header_bytes.strip().lower()
        if not lower.startswith(b"zyte-"):
            # Only Zyte-* control headers are passed through directly; they have
            # no api_params counterpart (e.g. Zyte-Client) or enable
            # forward-compatibility with proxy features not yet known to
            # scrapy-zyte-api.
            continue
        if lower == b"zyte-client":
            # Zyte-Client is filled automatically below; a user-defined value
            # (including an empty one, used to suppress the header) takes
            # precedence. Reading the raw values avoids Headers.get raising on
            # an empty value list (the None case).
            user_set_zyte_client = True
            values = request.headers.getlist(header_bytes)
            user_zyte_client = values[-1].decode() if values else ""
            continue
        header_name = header_bytes.decode()
        header_val = (request.headers.get(header_bytes) or b"").decode()
        lower_str = lower.decode()
        if lower == b"zyte-override-headers" and lower_str in param_lower_to_key:
            # A user-supplied Zyte-Override-Headers request header overrides the
            # value auto-generated from protected custom headers.
            if warn and lower not in _warned_conflict_headers:
                _warned_conflict_headers.add(lower)
                auto = proxy_headers[param_lower_to_key[lower_str]]
                logger.warning(
                    f"In {request!r}, the {header_name!r} request header (value "
                    f"{header_val!r}) overrides the value that would otherwise "
                    f"be generated automatically ({auto!r}) for protected "
                    f"headers. Those protected headers may be ignored by Zyte "
                    f"API unless they are also listed in the custom "
                    f"Zyte-Override-Headers value."
                )
            proxy_headers[param_lower_to_key[lower_str]] = header_val
            continue
        if (
            warn
            and lower in _ZYTE_HEADER_TO_PARAM
            and _param_is_set(api_params, lower)
            and lower not in _warned_conflict_headers
        ):
            _warned_conflict_headers.add(lower)
            param_name = _ZYTE_HEADER_TO_PARAM[lower]
            param_val = _get_raw_param_value(api_params, lower)
            logger.warning(
                f"In {request}, {param_name!r} is defined twice — as the "
                f"{header_name!r} proxy mode header (value "
                f"{header_val!r}) and as the {param_name!r} HTTP API "
                f"parameter (value {param_val!r}). The header takes "
                f"precedence."
            )
        proxy_headers[header_name] = header_val

    # Mirror the User-Agent used for the HTTP API as the proxy mode Zyte-Client
    # header, unless the user defined Zyte-Client themselves. A user-defined
    # empty value (None or "") suppresses the header entirely.
    if user_set_zyte_client:
        if user_zyte_client:
            proxy_headers["Zyte-Client"] = user_zyte_client
    elif user_agent:
        proxy_headers["Zyte-Client"] = user_agent

    return proxy_headers, proxy_method, proxy_body


def _build_proxy_request(
    proxy_url: str,
    api_key: str,
    request: Request,
    api_params: dict[str, Any],
    *,
    user_agent: str | None = USER_AGENT,
) -> Request:
    # The headers sent to the target are derived from the computed Zyte API
    # parameters (e.g. customHttpRequestHeaders, requestHeaders), exactly as
    # they would be sent through the HTTP API. The raw Request.headers are not
    # forwarded as-is: in automap mode they have already been mapped into those
    # parameters (with Scrapy/middleware default headers stripped), and in
    # manual mode they are not part of the request definition. This keeps both
    # transports consistent and prevents leaking default headers to the target.
    proxy_headers, proxy_method, proxy_body = _collect_proxy_headers(
        request, api_params, user_agent=user_agent
    )

    proxy_auth = b64encode(f"{api_key}:".encode()).decode()

    new_headers = {b"Proxy-Authorization": [f"Basic {proxy_auth}".encode()]}
    for header_name, header_val in proxy_headers.items():
        new_headers[header_name.encode()] = [header_val.encode()]

    new_meta = dict(request.meta)
    new_meta["proxy"] = proxy_url
    new_meta.pop("zyte_api", None)
    new_meta.pop("zyte_api_automap", None)
    new_meta.pop("zyte_api_transport", None)
    new_meta.pop("_zyte_api_transport_explicit", None)

    return request.replace(
        headers=new_headers,
        meta=new_meta,
        body=proxy_body if proxy_body is not None else request.body,
        method=proxy_method if proxy_method is not None else request.method,
    )


def _has_proxy_mode_headers(request: Request) -> bool:
    return any(header.lower().startswith(b"zyte-") for header in request.headers)


class ProxyModeError(RequestError):
    """Error raised when a Zyte API proxy request returns a Zyte-Error-Type header."""

    def __init__(self, response, *, query: dict[str, Any]):
        self._proxy_response = response
        raw_status = response.status
        raw_type = (response.headers.get(b"Zyte-Error-Type") or b"").decode()
        norm_type = _PROXY_TYPE_MAP.get(raw_type, raw_type)
        norm_status = _PROXY_STATUS_MAP.get(raw_status, raw_status)

        response_content = (
            json.dumps({"type": norm_type}).encode() if norm_type else b""
        )

        super().__init__(
            request_info=None,
            history=(),
            status=norm_status,
            message=f"Proxy error {raw_status}: {raw_type}",
            headers=response.headers,
            query=query,
            response_content=response_content,
        )

    @property
    def proxy_response(self):
        return self._proxy_response


class ProxyAggStats:
    """Mirrors AggStats interface; fed from proxy transport outcomes."""

    def __init__(self) -> None:
        self.time_connect_stats = Statistics()
        self.time_total_stats = Statistics()
        self.n_success = 0
        self.n_fatal_errors = 0
        self.n_attempts = 0
        self.n_429 = 0
        self.n_errors = 0
        self.n_402_req = 0
        self.status_codes: Counter[int] = Counter()
        self.exception_types: Counter[type] = Counter()
        self.api_error_types: Counter[str | None] = Counter()


def _zyte_browser_html_header_enabled(request: Request) -> bool:
    """Whether *request* carries a truthy ``Zyte-Browser-Html`` proxy header,
    interpreted with the same semantics as the Zyte API proxy server (see
    :func:`scrapy_zyte_api._utils.str_to_bool`)."""
    return str_to_bool((request.headers.get(b"Zyte-Browser-Html") or b"").decode())


def _proxy_uses_browser_rendering(request: Request, params: dict[str, Any]) -> bool:
    """Whether *request* invokes browser rendering in proxy mode, either through
    the ``browserHtml`` parameter or the ``Zyte-Browser-Html`` proxy header
    (which, in proxy mode, is left in the request rather than mapped to the
    parameter)."""
    if params.get("browserHtml"):
        return True
    return _zyte_browser_html_header_enabled(request)


def _is_proxy_mode_compatible(
    params: dict[str, Any], *, browser_rendering: bool = False
) -> bool:
    return not _get_proxy_incompatible_params(
        params, browser_rendering=browser_rendering
    )


def _check_for_proxy_error(response, query: dict[str, Any]) -> None:
    if response.headers.get(b"Zyte-Error-Type") is not None:
        raise ProxyModeError(response, query=query)


def _params_to_proxy_headers(
    params: dict[str, Any],
) -> tuple[dict[str, str], str | None, bytes | None]:
    """Convert Zyte API params to (headers, method, body)."""
    headers: dict[str, str] = {}
    method: str | None = None
    body: bytes | None = None

    for descriptor in _PROXY_HEADER_PARAMS:
        value = descriptor.to_header(params)
        if value is not None:
            headers[descriptor.header] = value

    request_headers = params.get("requestHeaders") or {}
    if referer := request_headers.get("referer"):
        headers["Referer"] = referer

    override_header_names: list[str] = []
    user_override_headers: str | None = None
    custom_headers = params.get("customHttpRequestHeaders") or []
    for h in custom_headers:
        name = h.get("name", "")
        if name:
            value = h.get("value", "")
            headers[name] = value
            lower_name = name.lower().encode()
            if lower_name in _PROTECTED_HEADERS:
                override_header_names.append(_PROTECTED_HEADERS[lower_name])
            elif lower_name == b"zyte-override-headers":
                user_override_headers = value

    if user_override_headers is not None:
        if override_header_names:
            logger.warning(
                f"A custom Zyte-Override-Headers value "
                f"({user_override_headers!r}) overrides the value that would "
                f"otherwise be generated automatically for the protected "
                f"headers {override_header_names!r}. Those protected headers "
                f"may be ignored by Zyte API unless they are also listed in the "
                f"custom Zyte-Override-Headers value."
            )
        headers["Zyte-Override-Headers"] = user_override_headers
    elif override_header_names:
        headers["Zyte-Override-Headers"] = ",".join(override_header_names)

    if (http_method := params.get("httpRequestMethod")) and http_method != "GET":
        method = http_method

    if body_b64 := params.get("httpRequestBody"):
        body = b64decode(body_b64)

    request_cookies = (
        params.get("requestCookies")
        or (params.get("experimental") or {}).get("requestCookies")
        or []
    )
    if request_cookies:
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in request_cookies)
        headers["Cookie"] = cookie_str

    return headers, method, body


def _estimate_proxy_header_section_size(
    request: Request,
    api_params: dict[str, Any],
    *,
    user_agent: str | None = USER_AGENT,
) -> int:
    """Estimate, in bytes, the request header section that proxy mode would emit
    for *request*, as counted by the Zyte API proxy's HTTP decoder.

    It reuses the exact header assembly of :func:`_build_proxy_request` (via
    :func:`_collect_proxy_headers`) but suppresses its warning side effects, so
    it is safe to call during transport resolution and cannot drift from what
    is actually sent. Headers it does not model are accounted for by
    :data:`_PROXY_HEADER_SECTION_RESERVE`.
    """
    headers, _, _ = _collect_proxy_headers(
        request, api_params, user_agent=user_agent, warn=False
    )
    return sum(
        len(name.encode()) + len(str(value).encode()) + _PROXY_HEADER_LINE_OVERHEAD
        for name, value in headers.items()
    )


def _proxy_headers_exceed_limit(
    request: Request,
    api_params: dict[str, Any],
    *,
    user_agent: str | None = USER_AGENT,
) -> bool:
    """Return whether the request header section that proxy mode would emit for
    *request* would exceed the Zyte API proxy's header-size limit and thus get a
    431 /request/header-size error."""
    size = _estimate_proxy_header_section_size(
        request, api_params, user_agent=user_agent
    )
    return size > _PROXY_HEADER_SECTION_LIMIT - _PROXY_HEADER_SECTION_RESERVE


class _ZyteAPIProxyMixin:
    if TYPE_CHECKING:
        url: str
        status: int
        body: bytes
        headers: Headers
        text: str
        _raw_api_response: dict | None

    def __init__(
        self,
        *args,
        proxy_request: Request | None = None,
        api_params: dict | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._proxy_request = proxy_request
        self._api_params = api_params

    @classmethod
    def from_proxy_response(
        cls,
        response: Response,
        *,
        request: Request | None = None,
        proxy_request: Request | None = None,
        api_params: dict | None = None,
    ):
        return cls(
            url=response.url,
            status=response.status,
            headers=response.headers,
            body=response.body,
            request=request or response.request,
            flags=[*response.flags, "zyte-api"],
            proxy_request=proxy_request,
            api_params=api_params,
        )

    @property
    def raw_api_response(self) -> dict | None:
        if self._raw_api_response is None:
            self._raw_api_response = self._build_raw_api_response()
        return self._raw_api_response

    def _build_raw_api_response(self) -> dict:
        result: dict = {"url": self.url, "statusCode": self.status}
        params = self._api_params or {}
        wants_top_cookies = bool(params.get("responseCookies"))
        wants_exp_cookies = bool(
            (params.get("experimental") or {}).get("responseCookies")
        )
        wants_cookies = wants_top_cookies or wants_exp_cookies
        if self._uses_browser_html():
            result["browserHtml"] = self.text
        else:
            result["httpResponseBody"] = b64encode(self.body).decode()
        headers = []
        for name, values in self.headers.items():
            name_str = name.decode() if isinstance(name, bytes) else name
            if name_str.lower().startswith("zyte-"):
                continue
            for value in values:
                value_str = value.decode() if isinstance(value, bytes) else value
                headers.append({"name": name_str, "value": value_str})
        result["httpResponseHeaders"] = headers
        if wants_cookies:
            # Response cookies are reconstructed from the proxied Set-Cookie
            # headers. This is only faithful for non-browser requests: the
            # dispatcher rejects responseCookies combined with browser
            # rendering (see _get_proxy_incompatible_params), because then these
            # headers would miss cookies set during rendering.
            cookies = []
            for raw in self.headers.getlist(b"Set-Cookie"):
                raw_str = raw.decode() if isinstance(raw, bytes) else raw
                parsed = _parse_set_cookie_header(raw_str)
                if parsed is not None:
                    cookies.append(parsed)
            if wants_top_cookies:
                result["responseCookies"] = cookies
            if wants_exp_cookies:
                result["experimental"] = {"responseCookies": cookies}
        return result

    def _uses_browser_html(self) -> bool:
        if self._proxy_request is None:
            return False
        return _zyte_browser_html_header_enabled(self._proxy_request)
