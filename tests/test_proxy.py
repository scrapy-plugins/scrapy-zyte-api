"""Unit tests for :mod:`scrapy_zyte_api._proxy` and the proxy-mode response
building in :mod:`scrapy_zyte_api.responses`."""

from __future__ import annotations

from base64 import b64encode

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse, Response, XmlResponse

from scrapy_zyte_api import _proxy as proxy_module
from scrapy_zyte_api._cookies import _parse_set_cookie_header
from scrapy_zyte_api._proxy import (
    ProxyAggStats,
    ProxyModeError,
    _build_proxy_request,
    _check_for_proxy_error,
    _get_proxy_incompatible_params,
    _get_raw_param_value,
    _get_unknown_proxy_mode_headers,
    _has_proxy_mode_headers,
    _is_proxy_mode_compatible,
    _params_to_proxy_headers,
)
from scrapy_zyte_api.responses import (
    ZyteAPIProxyJsonResponse,
    ZyteAPIProxyResponse,
    ZyteAPIProxyTextResponse,
    ZyteAPIProxyXmlResponse,
    _process_proxy_response,
)


@pytest.fixture(autouse=True)
def _reset_conflict_warnings():
    """``_build_proxy_request`` only warns once per process about each
    conflicting header; reset that state so tests are independent."""
    proxy_module._warned_conflict_headers.clear()
    yield
    proxy_module._warned_conflict_headers.clear()


# ----------------------------------------------------------------------------
# _parse_set_cookie_header
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (
            "foo=bar; Domain=example.com; Path=/x; Secure; HttpOnly; "
            "SameSite=Lax; Expires=Wed, 21 Oct 2025 07:28:00 GMT",
            {
                "name": "foo",
                "value": "bar",
                "domain": "example.com",
                "path": "/x",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": 1761031680,
            },
        ),
        ("foo=bar", {"name": "foo", "value": "bar"}),
        ("justname=", {"name": "justname", "value": ""}),
        # An unparseable Expires is suppressed rather than failing the parse.
        ("foo=bar; Expires=not-a-date", {"name": "foo", "value": "bar"}),
    ],
)
def test_parse_set_cookie(header, expected):
    assert _parse_set_cookie_header(header) == expected


@pytest.mark.parametrize("value", ["", "noequalsign", "; Domain=example.com"])
def test_parse_set_cookie_invalid(value):
    assert _parse_set_cookie_header(value) is None


def test_parse_set_cookie_whitespace_stripped():
    parsed = _parse_set_cookie_header("  foo = bar ; Domain = example.com ")
    assert parsed is not None
    assert parsed["name"] == "foo"
    assert parsed["value"] == "bar"
    assert parsed["domain"] == "example.com"


# ----------------------------------------------------------------------------
# _get_unknown_proxy_mode_headers / _has_proxy_mode_headers
# ----------------------------------------------------------------------------


def test_unknown_proxy_headers_none():
    request = Request(
        "https://example.com",
        headers={
            b"Zyte-Device": b"mobile",
            b"Zyte-Client": b"x",
            b"Zyte-Override-Headers": b"User-Agent",
            b"User-Agent": b"ua",
        },
    )
    assert _get_unknown_proxy_mode_headers(request) == []


def test_unknown_proxy_headers_some():
    request = Request(
        "https://example.com",
        headers={b"Zyte-Future-Feature": b"1", b"Zyte-Device": b"mobile"},
    )
    assert _get_unknown_proxy_mode_headers(request) == ["Zyte-Future-Feature"]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({b"Zyte-Device": b"mobile"}, True),
        ({b"Zyte-Foo": b"bar"}, True),
        ({b"User-Agent": b"ua"}, False),
        ({}, False),
    ],
)
def test_has_proxy_mode_headers(headers, expected):
    request = Request("https://example.com", headers=headers)
    assert _has_proxy_mode_headers(request) == expected


# ----------------------------------------------------------------------------
# _get_proxy_incompatible_params / _is_proxy_mode_compatible
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "incompatible"),
    [
        (
            {
                "url": "https://example.com",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "browserHtml": True,
                "device": "mobile",
                "geolocation": "US",
                "session": {"id": "x"},
                "javascript": True,
            },
            [],
        ),
        (
            {"url": "https://example.com", "product": True, "screenshot": True},
            ["product", "screenshot"],
        ),
        ({"javascript": False}, ["javascript"]),
        ({"javascript": True}, []),
        ({"experimental": {"responseCookies": True, "foo": 1}}, ["experimental.foo"]),
        ({"experimental": {}}, []),
    ],
)
def test_incompatible_params(params, incompatible):
    assert sorted(_get_proxy_incompatible_params(params)) == incompatible
    assert _is_proxy_mode_compatible(params) is (incompatible == [])


# ----------------------------------------------------------------------------
# _get_raw_param_value
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "params", "expected"),
    [
        (b"zyte-browser-html", {"browserHtml": True}, True),
        (b"zyte-cookie-management", {"cookieManagement": "discard"}, "discard"),
        (b"zyte-device", {"device": "mobile"}, "mobile"),
        (b"zyte-disable-follow-redirect", {"followRedirect": False}, False),
        (b"zyte-geolocation", {"geolocation": "US"}, "US"),
        (b"zyte-iptype", {"ipType": "residential"}, "residential"),
        (b"zyte-jobid", {"jobId": "j1"}, "j1"),
        (b"zyte-session-id", {"session": {"id": "s1"}}, "s1"),
        (b"zyte-session-id", {}, None),
        (b"zyte-tags", {"tags": {"a": "b"}}, {"a": "b"}),
        (b"zyte-unknown", {"device": "mobile"}, None),
    ],
)
def test_get_raw_param_value(header, params, expected):
    assert _get_raw_param_value(params, header) == expected


# ----------------------------------------------------------------------------
# _params_to_proxy_headers
# ----------------------------------------------------------------------------


def test_params_to_proxy_headers_full():
    params = {
        "url": "https://example.com",
        "browserHtml": True,
        "cookieManagement": "discard",
        "device": "mobile",
        "followRedirect": False,
        "geolocation": "US",
        "ipType": "residential",
        "jobId": "j1",
        "session": {"id": "s1"},
        "tags": {"a": "b"},
        "requestHeaders": {"referer": "https://ref"},
        "customHttpRequestHeaders": [
            {"name": "User-Agent", "value": "UA"},
            {"name": "X-Foo", "value": "bar"},
        ],
        "httpRequestMethod": "POST",
        "httpRequestBody": b64encode(b"hi").decode(),
        "requestCookies": [{"name": "c", "value": "v"}],
    }
    headers, method, body = _params_to_proxy_headers(params)
    assert headers["Zyte-Browser-Html"] == "true"
    assert headers["Zyte-Cookie-Management"] == "discard"
    assert headers["Zyte-Device"] == "mobile"
    assert headers["Zyte-Disable-Follow-Redirect"] == "true"
    assert headers["Zyte-Geolocation"] == "US"
    assert headers["Zyte-IPType"] == "residential"
    assert headers["Zyte-JobId"] == "j1"
    assert headers["Zyte-Session-ID"] == "s1"
    assert headers["Zyte-Tags"] == '{"a":"b"}'
    assert headers["Referer"] == "https://ref"
    assert headers["User-Agent"] == "UA"
    assert headers["X-Foo"] == "bar"
    assert headers["Zyte-Override-Headers"] == "User-Agent"
    assert headers["Cookie"] == "c=v"
    assert method == "POST"
    assert body == b"hi"


def test_params_to_proxy_headers_defaults_skipped():
    headers, method, body = _params_to_proxy_headers(
        {
            "url": "https://example.com",
            "device": "desktop",
            "cookieManagement": "auto",
            "followRedirect": True,
            "httpRequestMethod": "GET",
        }
    )
    assert "Zyte-Device" not in headers
    assert "Zyte-Cookie-Management" not in headers
    assert "Zyte-Disable-Follow-Redirect" not in headers
    assert method is None
    assert body is None


def test_params_to_proxy_headers_override_union():
    headers, _, _ = _params_to_proxy_headers(
        {
            "customHttpRequestHeaders": [
                {"name": "User-Agent", "value": "UA"},
                {"name": "Accept", "value": "*/*"},
            ],
            "requestHeaders": {},
        }
    )
    names = set(headers["Zyte-Override-Headers"].split(","))
    assert names == {"User-Agent", "Accept"}


@pytest.mark.parametrize(
    ("custom_headers", "warns"),
    [
        # A custom header literally named Zyte-Override-Headers overrides the
        # value that would be auto-generated from protected custom headers,
        # with a warning.
        (
            [
                {"name": "Zyte-Override-Headers", "value": "Accept-Language"},
                {"name": "User-Agent", "value": "UA"},
            ],
            True,
        ),
        # No protected headers to override: passed through without a warning.
        (
            [{"name": "Zyte-Override-Headers", "value": "Accept-Language"}],
            False,
        ),
        # The custom value already covers the protected headers: no warning.
        (
            [
                {"name": "Zyte-Override-Headers", "value": "Accept-Language"},
                {"name": "Accept-Language", "value": "gl"},
            ],
            False,
        ),
    ],
)
def test_params_to_proxy_headers_override(custom_headers, warns, caplog):
    with caplog.at_level("WARNING"):
        headers, _, _ = _params_to_proxy_headers(
            {"customHttpRequestHeaders": custom_headers}
        )
    assert headers["Zyte-Override-Headers"] == "Accept-Language"
    assert ("overrides the value" in caplog.text) is warns


def test_params_to_proxy_headers_experimental_cookies():
    headers, _, _ = _params_to_proxy_headers(
        {"experimental": {"requestCookies": [{"name": "c", "value": "v"}]}}
    )
    assert headers["Cookie"] == "c=v"


def test_params_to_proxy_headers_session_non_dict():
    headers, _, _ = _params_to_proxy_headers({"session": "not-a-dict"})
    assert "Zyte-Session-ID" not in headers


def test_params_to_proxy_headers_skips_unnamed_custom_header():
    headers, _, _ = _params_to_proxy_headers(
        {
            "customHttpRequestHeaders": [
                {"name": "", "value": "ignored"},
                {"name": "X-Foo", "value": "bar"},
            ]
        }
    )
    assert headers == {"X-Foo": "bar"}
    assert "Zyte-Override-Headers" not in headers


# ----------------------------------------------------------------------------
# _build_proxy_request
# ----------------------------------------------------------------------------


def test_build_proxy_request_basic():
    request = Request(
        "https://example.com",
        meta={
            "zyte_api": {},
            "zyte_api_automap": True,
            "zyte_api_transport": "proxy",
            "_zyte_api_transport_explicit": True,
            "foo": "bar",
        },
    )
    params = {
        "url": "https://example.com",
        "device": "mobile",
        "httpResponseBody": True,
    }
    proxy_request = _build_proxy_request("http://proxy:8011", "KEY", request, params)
    assert proxy_request.meta["proxy"] == "http://proxy:8011"
    assert proxy_request.meta["foo"] == "bar"
    # Zyte API routing meta is removed from the proxy-bound request.
    for key in (
        "zyte_api",
        "zyte_api_automap",
        "zyte_api_transport",
        "_zyte_api_transport_explicit",
    ):
        assert key not in proxy_request.meta
    assert proxy_request.headers[b"Proxy-Authorization"] == b"Basic " + b64encode(
        b"KEY:"
    )
    assert proxy_request.headers[b"Zyte-Device"] == b"mobile"


def test_build_proxy_request_passthrough_zyte_headers():
    request = Request(
        "https://example.com",
        headers={b"Zyte-Client": b"scrapy-zyte-api/1"},
        meta={"zyte_api_transport": "proxy"},
    )
    proxy_request = _build_proxy_request(
        "http://proxy:8011", "KEY", request, {"url": "https://example.com"}
    )
    assert proxy_request.headers[b"Zyte-Client"] == b"scrapy-zyte-api/1"


def test_build_proxy_request_ignores_non_zyte_request_headers():
    request = Request(
        "https://example.com",
        headers={b"User-Agent": b"raw-ua"},
        meta={"zyte_api_transport": "proxy"},
    )
    # _build_proxy_request derives target headers solely from api_params
    # (customHttpRequestHeaders/requestHeaders), never from raw
    # request.headers. Here User-Agent is only in request.headers and not in
    # params, so it must not leak. In real usage the param parser maps it into
    # customHttpRequestHeaders first, and from there it is forwarded raw.
    proxy_request = _build_proxy_request(
        "http://proxy:8011", "KEY", request, {"url": "https://example.com"}
    )
    assert b"User-Agent" not in proxy_request.headers


def test_build_proxy_request_body_and_method_fallback():
    request = Request(
        "https://example.com",
        method="PUT",
        body=b"original",
        meta={"zyte_api_transport": "proxy"},
    )
    # params define neither method nor body, so the request's own are kept.
    proxy_request = _build_proxy_request(
        "http://proxy:8011", "KEY", request, {"url": "https://example.com"}
    )
    assert proxy_request.method == "PUT"
    assert proxy_request.body == b"original"


def test_build_proxy_request_override_headers_replaces_auto(caplog):
    # A user-supplied Zyte-Override-Headers request header overrides the value
    # auto-generated from protected custom headers, with a warning.
    request = Request(
        "https://example.com",
        headers={b"Zyte-Override-Headers": b"Accept"},
        meta={"zyte_api_transport": "proxy"},
    )
    params = {
        "url": "https://example.com",
        "customHttpRequestHeaders": [{"name": "User-Agent", "value": "UA"}],
    }
    with caplog.at_level("WARNING"):
        proxy_request = _build_proxy_request(
            "http://proxy:8011", "KEY", request, params
        )
    assert proxy_request.headers[b"Zyte-Override-Headers"] == b"Accept"
    assert "overrides the value" in caplog.text


def test_build_proxy_request_conflict_warning(caplog):
    request = Request(
        "https://example.com",
        headers={b"Zyte-Device": b"mobile"},
        meta={"zyte_api_transport": "proxy"},
    )
    # Both the header and the param map to device, triggering a warning.
    params = {"url": "https://example.com", "device": "desktop"}
    with caplog.at_level("WARNING"):
        proxy_request = _build_proxy_request(
            "http://proxy:8011", "KEY", request, params
        )
    assert "'device' is defined twice" in caplog.text
    # The header wins.
    assert proxy_request.headers[b"Zyte-Device"] == b"mobile"


def test_build_proxy_request_conflict_warning_once(caplog):
    params = {"url": "https://example.com", "device": "desktop"}
    with caplog.at_level("WARNING"):
        for _ in range(2):
            request = Request(
                "https://example.com",
                headers={b"Zyte-Device": b"mobile"},
                meta={"zyte_api_transport": "proxy"},
            )
            _build_proxy_request("http://proxy:8011", "KEY", request, params)
    assert caplog.text.count("'device' is defined twice") == 1


# ----------------------------------------------------------------------------
# ProxyModeError / _check_for_proxy_error
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_status", "raw_type", "exp_status", "exp_type"),
    [
        (407, "/auth/proxy-auth-not-valid", 401, "/auth/key-not-found"),
        (431, "/request/header-size", 400, "/request/invalid"),
        (520, "/download/temporary-error", 520, "/download/temporary-error"),
        (500, "", 500, ""),
    ],
)
def test_proxy_mode_error_mapping(raw_status, raw_type, exp_status, exp_type):
    headers = {b"Zyte-Error-Type": raw_type.encode()} if raw_type else {}
    response = Response("https://example.com", status=raw_status, headers=headers)
    error = ProxyModeError(response, query={"url": "https://example.com"})
    assert error.status == exp_status
    assert error.parsed.type == (exp_type or None)
    assert error.proxy_response is response
    assert str(raw_status) in error.message


def test_check_for_proxy_error_raises():
    response = Response(
        "https://example.com",
        status=520,
        headers={b"Zyte-Error-Type": b"/download/temporary-error"},
    )
    with pytest.raises(ProxyModeError):
        _check_for_proxy_error(response, query={"url": "https://example.com"})


def test_check_for_proxy_error_no_error():
    response = Response("https://example.com", status=200)
    # Must not raise.
    _check_for_proxy_error(response, query={"url": "x"})


# ----------------------------------------------------------------------------
# ProxyAggStats
# ----------------------------------------------------------------------------


def test_proxy_agg_stats_init():
    stats = ProxyAggStats()
    assert stats.n_success == 0
    assert stats.n_fatal_errors == 0
    assert stats.n_attempts == 0
    assert stats.n_429 == 0
    assert stats.n_errors == 0
    assert stats.n_402_req == 0
    assert stats.status_codes == {}
    assert stats.exception_types == {}
    assert stats.api_error_types == {}


# ----------------------------------------------------------------------------
# Response building (_ZyteAPIProxyMixin / _process_proxy_response)
# ----------------------------------------------------------------------------


def test_process_proxy_response_browser_html():
    request = Request("https://example.com")
    proxy_request = Request(
        "https://example.com", headers={b"Zyte-Browser-Html": b"true"}
    )
    raw = HtmlResponse(
        "https://example.com",
        body=b"<html><body>hi</body></html>",
        encoding="utf-8",
        headers={b"Content-Type": b"text/html"},
    )
    response = _process_proxy_response(
        raw, request, proxy_request, {"browserHtml": True}
    )
    assert isinstance(response, ZyteAPIProxyTextResponse)
    assert response._uses_browser_html() is True
    assert "zyte-api" in response.flags
    raw_api = response.raw_api_response
    assert raw_api is not None
    assert raw_api["browserHtml"] == "<html><body>hi</body></html>"
    assert "httpResponseBody" not in raw_api


def test_process_proxy_response_http_body_filters_headers():
    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = Response(
        "https://example.com",
        body=b"hello",
        headers={
            b"Content-Type": b"text/html",
            b"Set-Cookie": b"a=b",
            b"Zyte-Request-Id": b"abc",
        },
    )
    response = _process_proxy_response(
        raw, request, proxy_request, {"httpResponseBody": True}
    )
    assert isinstance(response, ZyteAPIProxyResponse)
    raw_api = response.raw_api_response
    assert raw_api is not None
    assert raw_api["httpResponseBody"] == b64encode(b"hello").decode()
    header_names = {h["name"].lower() for h in raw_api["httpResponseHeaders"]}
    # Zyte-* response headers are stripped; Set-Cookie kept (cookies not asked).
    assert "zyte-request-id" not in header_names
    assert "set-cookie" in header_names


def test_process_proxy_response_response_cookies():
    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = Response(
        "https://example.com",
        body=b"hello",
        headers={b"Set-Cookie": b"a=b; Domain=example.com"},
    )
    response = _process_proxy_response(
        raw, request, proxy_request, {"httpResponseBody": True, "responseCookies": True}
    )
    raw_api = response.raw_api_response
    assert raw_api is not None
    assert raw_api["responseCookies"] == [
        {"name": "a", "value": "b", "domain": "example.com"}
    ]
    # When cookies are requested, Set-Cookie is removed from the headers.
    header_names = {h["name"].lower() for h in raw_api["httpResponseHeaders"]}
    assert "set-cookie" not in header_names


def test_process_proxy_response_skips_unparseable_cookie():
    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = Response(
        "https://example.com",
        body=b"hello",
        headers={b"Set-Cookie": [b"valid=1", b"garbage-without-equals"]},
    )
    response = _process_proxy_response(
        raw, request, proxy_request, {"httpResponseBody": True, "responseCookies": True}
    )
    raw_api = response.raw_api_response
    assert raw_api is not None
    assert raw_api["responseCookies"] == [{"name": "valid", "value": "1"}]


def test_process_proxy_response_experimental_response_cookies():
    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = Response(
        "https://example.com",
        body=b"hello",
        headers={b"Set-Cookie": b"a=b"},
    )
    response = _process_proxy_response(
        raw,
        request,
        proxy_request,
        {"httpResponseBody": True, "experimental": {"responseCookies": True}},
    )
    raw_api = response.raw_api_response
    assert isinstance(raw_api, dict)
    assert "responseCookies" not in raw_api
    assert raw_api["experimental"]["responseCookies"] == [{"name": "a", "value": "b"}]


def test_proxy_response_uses_browser_html_no_proxy_request():
    raw = HtmlResponse("https://example.com", body=b"<html></html>", encoding="utf-8")
    response = ZyteAPIProxyTextResponse.from_proxy_response(raw)
    assert response._uses_browser_html() is False


def test_proxy_response_raw_api_response_cached():
    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = Response("https://example.com", body=b"hello")
    response = _process_proxy_response(
        raw, request, proxy_request, {"httpResponseBody": True}
    )
    first = response.raw_api_response
    assert response.raw_api_response is first


@pytest.mark.parametrize(
    ("raw_cls", "kwargs", "expected_cls"),
    [
        (
            HtmlResponse,
            {"body": b"<html></html>", "encoding": "utf-8"},
            ZyteAPIProxyTextResponse,
        ),
        (
            XmlResponse,
            {"body": b"<root/>", "encoding": "utf-8"},
            ZyteAPIProxyXmlResponse,
        ),
        (Response, {"body": b"data"}, ZyteAPIProxyResponse),
    ],
)
def test_process_proxy_response_dispatch(raw_cls, kwargs, expected_cls):
    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = raw_cls("https://example.com", **kwargs)
    response = _process_proxy_response(
        raw, request, proxy_request, {"httpResponseBody": True}
    )
    assert type(response) is expected_cls


@pytest.mark.skipif(ZyteAPIProxyJsonResponse is None, reason="Scrapy < 2.12")
def test_process_proxy_response_json():
    from scrapy.http import JsonResponse  # noqa: PLC0415

    request = Request("https://example.com")
    proxy_request = Request("https://example.com")
    raw = JsonResponse("https://example.com", body=b'{"a": 1}', encoding="utf-8")
    response = _process_proxy_response(
        raw, request, proxy_request, {"httpResponseBody": True}
    )
    assert type(response) is ZyteAPIProxyJsonResponse


def test_from_proxy_response_uses_response_request_by_default():
    inner_request = Request("https://example.com")
    raw = Response("https://example.com", body=b"data", request=inner_request)
    response = ZyteAPIProxyResponse.from_proxy_response(raw)
    assert response.request is inner_request
