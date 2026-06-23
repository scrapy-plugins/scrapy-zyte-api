"""Handler-level tests for proxy-mode dispatch, stats, warnings and errors."""

from __future__ import annotations

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse, Response
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api._proxy import ProxyModeError
from scrapy_zyte_api.responses import ZyteAPIProxyResponse, ZyteAPIProxyTextResponse
from scrapy_zyte_api.utils import USER_AGENT

from . import SETTINGS, SETTINGS_T, download_request

# ZYTE_API_RETRY_POLICY is deliberately left unset: proxy mode must fall back
# to the client's default retry policy, just like the HTTP API path does.
PROXY_SETTINGS: SETTINGS_T = {
    **SETTINGS,
    "ZYTE_API_TRANSPORT": "proxy",
}


def _patch_fallback(handler, response=None, exc=None):
    """Replace the handler's fallback download with a controllable coroutine
    that simulates the response coming back from the proxy endpoint."""
    calls = []

    async def fake_fallback(request, spider=None):
        calls.append(request)
        if exc is not None:
            raise exc
        return response

    handler._download_via_fallback = fake_fallback
    return calls


def _proxy_target_response(
    url="https://example.com", *, html=False, status=200, headers=None
):
    hdrs = {b"Content-Type": [b"text/html"]}
    if headers:
        hdrs.update(headers)
    cls = HtmlResponse if html else Response
    kwargs = {"status": status, "headers": hdrs, "body": b"<html>hi</html>"}
    if html:
        kwargs["encoding"] = "utf-8"
    return cls(url, **kwargs)


# ----------------------------------------------------------------------------
# Transport routing + stats
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "meta"),
    [
        ({**SETTINGS, "ZYTE_API_TRANSPORT": "http"}, {"zyte_api_automap": True}),
        # A manual request ignores ZYTE_API_TRANSPORT=proxy and uses the HTTP API.
        (PROXY_SETTINGS, {"zyte_api": {}}),
    ],
    ids=["explicit_http", "manual_defaults_to_http"],
)
@deferred_f_from_coro_f
async def test_dispatch_uses_http(mockserver, settings, meta):
    async with mockserver.make_handler(settings) as handler:
        request = Request(mockserver.urljoin("/"), meta=meta)
        await download_request(handler, request)
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/http") == 1
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/proxy") is None


@deferred_f_from_coro_f
async def test_dispatch_proxy_transport_success(mockserver):
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(handler, response=_proxy_target_response())
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        response = await download_request(handler, request)
    assert isinstance(response, ZyteAPIProxyResponse)
    assert "zyte-api" in response.flags
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/proxy") == 1
    assert handler._stats.get_value("scrapy-zyte-api/success") == 1
    assert handler._stats.get_value("scrapy-zyte-api/processed") == 1
    assert handler._proxy_agg_stats.n_success == 1
    assert handler._proxy_agg_stats.n_attempts == 1


@deferred_f_from_coro_f
async def test_proxy_zyte_client_default(mockserver):
    # The proxy request carries Zyte-Client filled with the HTTP API User-Agent.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        calls = _patch_fallback(handler, response=_proxy_target_response())
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        await download_request(handler, request)
    assert calls[0].headers[b"Zyte-Client"] == USER_AGENT.encode()


@deferred_f_from_coro_f
async def test_proxy_zyte_client_custom_user_agent(mockserver):
    # A custom HTTP API User-Agent is mirrored into Zyte-Client.
    settings: SETTINGS_T = {**PROXY_SETTINGS, "_ZYTE_API_USER_AGENT": "my-crawler/1.0"}
    async with mockserver.make_handler(settings) as handler:
        calls = _patch_fallback(handler, response=_proxy_target_response())
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        await download_request(handler, request)
    assert calls[0].headers[b"Zyte-Client"] == b"my-crawler/1.0"


@deferred_f_from_coro_f
async def test_proxy_uses_client_retry_policy_by_default(mockserver):
    # Make sure not defining a retry policy does not make things crash.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        assert handler._retry_policy is None
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        _patch_fallback(handler, response=_proxy_target_response())
        response = await download_request(handler, request)
    assert isinstance(response, ZyteAPIProxyResponse)
    assert handler._proxy_agg_stats.n_success == 1


@deferred_f_from_coro_f
async def test_dispatch_proxy_transport_html(mockserver):
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(handler, response=_proxy_target_response(html=True))
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        response = await download_request(handler, request)
    assert isinstance(response, ZyteAPIProxyTextResponse)


@deferred_f_from_coro_f
async def test_proxy_request_args_stats(mockserver):
    """request_args stats reflect the actual Zyte API parameters in proxy
    mode, including those carried as Zyte-* headers (counted under their HTTP
    API parameter names) and parameters that are implicit in proxy mode."""
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(handler, response=_proxy_target_response())
        request = Request(
            mockserver.urljoin("/"),
            method="POST",
            body=b"hello",
            headers={b"Zyte-Device": b"mobile", b"Zyte-Geolocation": b"US"},
        )
        await download_request(handler, request)
    stats = handler._stats
    # Explicit request parameters, including those carried as Zyte-* headers.
    assert stats.get_value("scrapy-zyte-api/request_args/url") == 1
    assert stats.get_value("scrapy-zyte-api/request_args/httpRequestMethod") == 1
    assert stats.get_value("scrapy-zyte-api/request_args/httpRequestBody") == 1
    assert stats.get_value("scrapy-zyte-api/request_args/device") == 1
    assert stats.get_value("scrapy-zyte-api/request_args/geolocation") == 1
    # Implicit request parameters: for a non-browser request, the response body
    # and headers are always returned, so they are always counted.
    assert stats.get_value("scrapy-zyte-api/request_args/httpResponseBody") == 1
    assert stats.get_value("scrapy-zyte-api/request_args/httpResponseHeaders") == 1
    # responseCookies is not implicit: it is only counted when actually used.
    assert stats.get_value("scrapy-zyte-api/request_args/responseCookies") is None


@pytest.mark.parametrize(
    ("headers", "meta"),
    [
        # browserHtml requested as a parameter.
        ({}, {"zyte_api_automap": {"browserHtml": True}}),
        # browserHtml requested as a Zyte-* proxy header.
        ({b"Zyte-Browser-Html": b"true"}, {"zyte_api_automap": True}),
    ],
    ids=["param", "header"],
)
@deferred_f_from_coro_f
async def test_proxy_request_args_stats_browser(mockserver, headers, meta):
    """With browser rendering, browserHtml is the implicit output, so
    httpResponseBody/httpResponseHeaders are NOT counted as implicit."""
    settings = {**PROXY_SETTINGS, "ZYTE_API_HEADER_TRANSPORT_ENABLED": True}
    async with mockserver.make_handler(settings) as handler:
        _patch_fallback(handler, response=_proxy_target_response(html=True))
        request = Request(mockserver.urljoin("/"), headers=headers, meta=meta)
        await download_request(handler, request)
    stats = handler._stats
    assert stats.get_value("scrapy-zyte-api/request_args/url") == 1
    assert stats.get_value("scrapy-zyte-api/request_args/browserHtml") == 1
    # browserHtml is the response body, so httpResponseBody is not implicit and
    # must not be counted.
    assert stats.get_value("scrapy-zyte-api/request_args/httpResponseBody") is None
    # httpResponseHeaders stays implicit: proxy mode always returns the HTTP
    # response headers, even for browser requests.
    assert stats.get_value("scrapy-zyte-api/request_args/httpResponseHeaders") == 1


# ----------------------------------------------------------------------------
# Experimental gating warnings + stats
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "request_kwargs",
        "stat_key",
        "warning_substring",
        "extra_substring",
        "http_count",
    ),
    [
        # Eligible for proxy, but transport not explicitly configured.
        (
            {"meta": {"zyte_api_automap": True}},
            "scrapy-zyte-api/request/transport/proxy/experimental",
            "proxy mode support is currently",
            "ZYTE_API_TRANSPORT",
            2,
        ),
        # Eligible for proxy because of a Zyte-* header.
        (
            {"headers": {b"Zyte-Device": b"mobile"}},
            "scrapy-zyte-api/request/transport/proxy/experimental/header",
            "ZYTE_API_HEADER_TRANSPORT_ENABLED",
            None,
            None,
        ),
    ],
    ids=["transport", "header"],
)
@deferred_f_from_coro_f
async def test_experimental_warning(
    mockserver,
    caplog,
    request_kwargs,
    stat_key,
    warning_substring,
    extra_substring,
    http_count,
):
    async with mockserver.make_handler({**SETTINGS}) as handler:
        with caplog.at_level("WARNING"):
            for _ in range(2):
                request = Request(mockserver.urljoin("/"), **request_kwargs)
                await download_request(handler, request)
    assert handler._stats.get_value(stat_key) == 2
    if http_count is not None:
        assert (
            handler._stats.get_value("scrapy-zyte-api/request/transport/http")
            == http_count
        )
    # The warning is logged at most once.
    assert caplog.text.count(warning_substring) == 1
    if extra_substring is not None:
        assert extra_substring in caplog.text


@deferred_f_from_coro_f
async def test_no_experimental_warning_when_explicit(mockserver, caplog):
    settings: SETTINGS_T = {**SETTINGS, "ZYTE_API_TRANSPORT": "http"}
    async with mockserver.make_handler(settings) as handler:
        with caplog.at_level("WARNING"):
            request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
            await download_request(handler, request)
    assert (
        handler._stats.get_value("scrapy-zyte-api/request/transport/proxy/experimental")
        is None
    )
    assert "proxy mode support is currently" not in caplog.text


# ----------------------------------------------------------------------------
# Proxy-incompatible parameter errors
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "headers", "meta", "match"),
    [
        # An explicitly proxy-incompatible parameter (screenshot).
        (
            PROXY_SETTINGS,
            None,
            {"zyte_api_automap": {"screenshot": True}},
            "not supported in proxy mode",
        ),
        # Auto transport with an unknown Zyte-* header alongside a
        # proxy-incompatible parameter.
        (
            {**SETTINGS},
            {b"Zyte-Future-Feature": b"1"},
            {"zyte_api_automap": {"screenshot": True}, "zyte_api_transport": "auto"},
            r"unknown Zyte-\* headers",
        ),
    ],
    ids=["explicit", "auto_unknown_header"],
)
@deferred_f_from_coro_f
async def test_proxy_incompatible_error(mockserver, settings, headers, meta, match):
    async with mockserver.make_handler(settings) as handler:
        request = Request(mockserver.urljoin("/"), headers=headers, meta=meta)
        with pytest.raises(ValueError, match=match):
            await download_request(handler, request)


# Cookie parameters combined with browser rendering: proxy mode cannot
# represent the browser cookie jar, so an explicit proxy request must hard-error
# (and an "auto" request must fall back to the HTTP API).
@pytest.mark.parametrize(
    "automap",
    [
        {"browserHtml": True, "responseCookies": True},
        {"browserHtml": True, "requestCookies": [{"name": "a", "value": "b"}]},
        {"browserHtml": True, "experimental": {"responseCookies": True}},
        {
            "browserHtml": True,
            "experimental": {"requestCookies": [{"name": "a", "value": "b"}]},
        },
    ],
)
@deferred_f_from_coro_f
async def test_proxy_cookies_with_browser_rendering_error(mockserver, automap):
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": automap})
        with pytest.raises(ValueError, match="without browser rendering"):
            await download_request(handler, request)


@deferred_f_from_coro_f
async def test_proxy_cookies_with_browser_rendering_via_header_error(mockserver):
    # browserHtml carried as a Zyte-* proxy header (not as a parameter).
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        request = Request(
            mockserver.urljoin("/"),
            headers={b"Zyte-Browser-Html": b"true"},
            meta={"zyte_api_automap": {"responseCookies": True}},
        )
        with pytest.raises(ValueError, match="without browser rendering"):
            await download_request(handler, request)


@deferred_f_from_coro_f
async def test_proxy_response_cookies_without_browser_ok(mockserver):
    # responseCookies without browser rendering stays proxy-compatible, and is
    # reconstructed from the proxied Set-Cookie headers.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        response = _proxy_target_response(headers={b"Set-Cookie": [b"a=b"]})
        _patch_fallback(handler, response=response)
        request = Request(
            mockserver.urljoin("/"),
            meta={"zyte_api_automap": {"responseCookies": True}},
        )
        result = await download_request(handler, request)
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/proxy") == 1
    assert isinstance(result, ZyteAPIProxyResponse)
    raw_api = result.raw_api_response
    assert raw_api is not None
    assert raw_api["responseCookies"] == [{"name": "a", "value": "b"}]


@deferred_f_from_coro_f
async def test_proxy_browser_rendering_without_cookies_ok(mockserver):
    # browserHtml without cookie parameters stays proxy-compatible.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(handler, response=_proxy_target_response(html=True))
        request = Request(
            mockserver.urljoin("/"), meta={"zyte_api_automap": {"browserHtml": True}}
        )
        await download_request(handler, request)
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/proxy") == 1


@deferred_f_from_coro_f
async def test_auto_cookies_with_browser_rendering_falls_back_to_http(mockserver):
    # An "auto" request with cookies + browser rendering is not proxy-compatible,
    # so it uses the HTTP API (no error, no proxy transport).
    async with mockserver.make_handler({**SETTINGS}) as handler:
        request = Request(
            mockserver.urljoin("/"),
            meta={
                "zyte_api_automap": {"browserHtml": True, "responseCookies": True},
                "zyte_api_transport": "auto",
            },
        )
        await download_request(handler, request)
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/http") == 1
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/proxy") is None


# ----------------------------------------------------------------------------
# Proxy error handling
# ----------------------------------------------------------------------------


@deferred_f_from_coro_f
async def test_proxy_mode_error(mockserver):
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        error_response = _proxy_target_response(
            status=403,
            headers={b"Zyte-Error-Type": [b"/auth/account-suspended"]},
        )
        _patch_fallback(handler, response=error_response)
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        with pytest.raises(ProxyModeError):
            await download_request(handler, request)
    assert handler._proxy_agg_stats.n_fatal_errors == 1
    assert handler._stats.get_value("scrapy-zyte-api/fatal_errors") == 1


@deferred_f_from_coro_f
async def test_proxy_response_body_max_size_exceeded(mockserver):
    # A proxy response whose body exceeds DOWNLOAD_MAXSIZE is dropped (None),
    # mirroring the HTTP API path.
    settings: SETTINGS_T = {**PROXY_SETTINGS, "DOWNLOAD_MAXSIZE": 5}
    async with mockserver.make_handler(settings) as handler:
        _patch_fallback(handler, response=_proxy_target_response())
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        response = await download_request(handler, request)
    assert response is None


@deferred_f_from_coro_f
async def test_attempt_via_proxy_counts_429(mockserver):
    # A proxy 429 error increments the throttling counter rather than n_errors.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(
            handler,
            response=_proxy_target_response(
                status=429,
                headers={b"Zyte-Error-Type": [b"/limits/over-global-limit"]},
            ),
        )
        proxy_request = Request(mockserver.urljoin("/"))
        with pytest.raises(ProxyModeError):
            await handler._attempt_via_proxy(proxy_request)
    assert handler._proxy_agg_stats.n_429 == 1
    assert handler._proxy_agg_stats.n_errors == 0
    assert handler._proxy_agg_stats.status_codes[429] == 1


@deferred_f_from_coro_f
async def test_update_stats_error_type_without_leading_slash(mockserver):
    # An API error type that is not slash-prefixed is normalized to one in the
    # error_types stat key.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(
            handler,
            response=_proxy_target_response(
                status=520,
                headers={b"Zyte-Error-Type": [b"weird-no-slash"]},
            ),
        )
        proxy_request = Request(mockserver.urljoin("/"))
        with pytest.raises(ProxyModeError):
            await handler._attempt_via_proxy(proxy_request)
        handler._update_stats({})
    assert handler._stats.get_value("scrapy-zyte-api/error_types/weird-no-slash") == 1


@deferred_f_from_coro_f
async def test_update_stats_missing_proxy_counter(mockserver):
    # _update_stats tolerates an http n_* counter that has no proxy
    # counterpart, treating the proxy contribution as zero.
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        handler._client.agg_stats.n_http_only = 5
        handler._update_stats({})
    assert handler._stats.get_value("scrapy-zyte-api/http_only") == 5


@deferred_f_from_coro_f
async def test_proxy_transport_exception_counts_fatal(mockserver):
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        _patch_fallback(handler, exc=RuntimeError("boom"))
        request = Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True})
        with pytest.raises(RuntimeError):
            await download_request(handler, request)
    assert handler._proxy_agg_stats.n_fatal_errors == 1
    assert handler._proxy_agg_stats.n_errors == 1
    assert RuntimeError in handler._proxy_agg_stats.exception_types


# ----------------------------------------------------------------------------
# Combined stats (HTTP API + proxy)
# ----------------------------------------------------------------------------


@deferred_f_from_coro_f
async def test_proxy_request_logging(mockserver, caplog):
    settings: SETTINGS_T = {**PROXY_SETTINGS, "ZYTE_API_LOG_REQUESTS": True}
    async with mockserver.make_handler(settings) as handler:
        _patch_fallback(handler, response=_proxy_target_response())
        request = Request(
            mockserver.urljoin("/"),
            headers={b"Zyte-Device": b"mobile"},
            meta={"zyte_api_automap": True},
        )
        with caplog.at_level("DEBUG"):
            await download_request(handler, request)
    assert "Sending Zyte API proxy request" in caplog.text
    # Only Zyte-* headers are logged for proxy requests.
    assert "Zyte-Device" in caplog.text


@deferred_f_from_coro_f
async def test_combined_stats(mockserver):
    async with mockserver.make_handler(PROXY_SETTINGS) as handler:
        # One proxy request...
        _patch_fallback(handler, response=_proxy_target_response())
        await download_request(
            handler,
            Request(mockserver.urljoin("/"), meta={"zyte_api_automap": True}),
        )
        # ...and one HTTP API request (manual, so it uses the real fallback-less
        # HTTP API path against the mockserver).
        await download_request(
            handler,
            Request(mockserver.urljoin("/"), meta={"zyte_api": {}}),
        )
    # success counts both transports.
    assert handler._stats.get_value("scrapy-zyte-api/success") == 2
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/proxy") == 1
    assert handler._stats.get_value("scrapy-zyte-api/request/transport/http") == 1
    assert 0.0 <= handler._stats.get_value("scrapy-zyte-api/success_ratio") <= 1.0
