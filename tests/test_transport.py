"""Tests for request-transport resolution
(:mod:`scrapy_zyte_api._request_transport` and
:mod:`scrapy_zyte_api._request_type`) and the transport-related parts of
:class:`scrapy_zyte_api._params._ParamParser`."""

from __future__ import annotations

import pytest
from scrapy import Request, Spider
from scrapy.settings import Settings
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api._params import _ParamParser, _smartproxy_enabled
from scrapy_zyte_api._request_transport import (
    _get_assigned_transport,
    _header_is_decisive,
    _resolve_auto_transport,
    _resolve_configured_transport,
    _resolve_transport,
    _transport_is_explicit,
    _validate_transport,
)
from scrapy_zyte_api._request_type import is_manual_request

from . import get_crawler

COMPATIBLE_PARAMS = {"url": "https://example.com", "httpResponseBody": True}
INCOMPATIBLE_PARAMS = {"url": "https://example.com", "product": True}


def settings(**kwargs) -> Settings:
    return Settings(kwargs)


# ----------------------------------------------------------------------------
# is_manual_request
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"zyte_api": True}, True),
        ({"zyte_api": {"browserHtml": True}}, True),
        ({"zyte_api": False}, False),
        ({"zyte_api": None}, False),
        ({}, False),
        ({"zyte_api_automap": True}, False),
    ],
)
def test_is_manual_request(meta, expected):
    assert is_manual_request(Request("https://example.com", meta=meta)) is expected


# ----------------------------------------------------------------------------
# _validate_transport
# ----------------------------------------------------------------------------


@pytest.mark.parametrize("transport", ["auto", "http", "proxy"])
def test_validate_transport_valid(transport):
    assert _validate_transport(transport, source="x") == transport


def test_validate_transport_invalid():
    with pytest.raises(ValueError, match="Invalid request transport 'bogus'"):
        _validate_transport("bogus", source="the test source")


# ----------------------------------------------------------------------------
# _resolve_configured_transport
# ----------------------------------------------------------------------------


def _resolve_configured(meta_value=None, setting_value=None):
    return _resolve_configured_transport(
        meta_value=meta_value,
        setting_value=setting_value,
        meta_source="the test meta key",
        setting_source="the TEST setting",
    )


def test_resolve_configured_transport_default():
    # Neither configured: defaults to "auto" and is flagged non-explicit.
    assert _resolve_configured() == ("auto", False)


def test_resolve_configured_transport_setting():
    assert _resolve_configured(setting_value="proxy") == ("proxy", True)


def test_resolve_configured_transport_meta_precedence():
    # The meta value takes precedence over the setting value.
    assert _resolve_configured(meta_value="http", setting_value="proxy") == (
        "http",
        True,
    )


def test_resolve_configured_transport_invalid_meta():
    with pytest.raises(ValueError, match="the test meta key"):
        _resolve_configured(meta_value="bogus")


def test_resolve_configured_transport_invalid_setting():
    with pytest.raises(ValueError, match="the TEST setting"):
        _resolve_configured(setting_value="bogus")


# ----------------------------------------------------------------------------
# _get_assigned_transport
# ----------------------------------------------------------------------------


def test_get_assigned_transport_meta():
    request = Request("https://example.com", meta={"zyte_api_transport": "proxy"})
    assert _get_assigned_transport(request, settings()) == "proxy"


def test_get_assigned_transport_manual_defaults_http():
    # A manual request ignores ZYTE_API_TRANSPORT and defaults to http.
    request = Request("https://example.com", meta={"zyte_api": {}})
    assert (
        _get_assigned_transport(request, settings(ZYTE_API_TRANSPORT="proxy")) == "http"
    )


def test_get_assigned_transport_manual_meta_override():
    request = Request(
        "https://example.com",
        meta={"zyte_api": {}, "zyte_api_transport": "proxy"},
    )
    assert _get_assigned_transport(request, settings()) == "proxy"


def test_get_assigned_transport_setting():
    request = Request("https://example.com", meta={"zyte_api_automap": True})
    assert (
        _get_assigned_transport(request, settings(ZYTE_API_TRANSPORT="proxy"))
        == "proxy"
    )


def test_get_assigned_transport_default_auto():
    request = Request("https://example.com")
    assert _get_assigned_transport(request, settings()) == "auto"


def test_get_assigned_transport_invalid_meta():
    request = Request("https://example.com", meta={"zyte_api_transport": "bogus"})
    with pytest.raises(ValueError, match=r"zyte_api_transport request\.meta key"):
        _get_assigned_transport(request, settings())


def test_get_assigned_transport_invalid_setting():
    request = Request("https://example.com")
    with pytest.raises(ValueError, match="ZYTE_API_TRANSPORT setting"):
        _get_assigned_transport(request, settings(ZYTE_API_TRANSPORT="bogus"))


# ----------------------------------------------------------------------------
# _transport_is_explicit
# ----------------------------------------------------------------------------


def test_transport_is_explicit_flag_true():
    request = Request(
        "https://example.com", meta={"_zyte_api_transport_explicit": True}
    )
    assert _transport_is_explicit(request, settings()) is True


def test_transport_is_explicit_flag_false():
    request = Request(
        "https://example.com",
        meta={"_zyte_api_transport_explicit": False, "zyte_api_transport": "auto"},
    )
    # The explicit flag wins over the presence of zyte_api_transport.
    assert _transport_is_explicit(request, settings()) is False


def test_transport_is_explicit_meta_transport():
    request = Request("https://example.com", meta={"zyte_api_transport": "auto"})
    assert _transport_is_explicit(request, settings()) is True


def test_transport_is_explicit_manual_is_not():
    request = Request("https://example.com", meta={"zyte_api": {}})
    assert _transport_is_explicit(request, settings()) is False


def test_transport_is_explicit_setting():
    request = Request("https://example.com", meta={"zyte_api_automap": True})
    assert _transport_is_explicit(request, settings(ZYTE_API_TRANSPORT="auto")) is True


def test_transport_is_explicit_header_with_setting_enabled():
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert (
        _transport_is_explicit(
            request, settings(ZYTE_API_HEADER_TRANSPORT_ENABLED=True)
        )
        is True
    )


def test_transport_is_explicit_header_without_setting():
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert _transport_is_explicit(request, settings()) is False


def test_transport_is_explicit_no_signal():
    request = Request("https://example.com")
    assert _transport_is_explicit(request, settings()) is False


# ----------------------------------------------------------------------------
# _resolve_auto_transport
# ----------------------------------------------------------------------------


def test_resolve_auto_transport_non_zyte_auth():
    request = Request("https://example.com")
    assert _resolve_auto_transport(request, COMPATIBLE_PARAMS, "apikey") == "http"


def test_resolve_auto_transport_compatible():
    request = Request("https://example.com")
    assert _resolve_auto_transport(request, COMPATIBLE_PARAMS, "zyte") == "proxy"


def test_resolve_auto_transport_incompatible_falls_back():
    request = Request("https://example.com")
    assert _resolve_auto_transport(request, INCOMPATIBLE_PARAMS, "zyte") == "http"


def test_resolve_auto_transport_incompatible_with_unknown_header():
    request = Request("https://example.com", headers={b"Zyte-Future": b"1"})
    # Cannot fall back to HTTP API because the unknown header cannot be honored.
    assert _resolve_auto_transport(request, INCOMPATIBLE_PARAMS, "zyte") == "proxy"


# Proxy-compatible, but the header section proxy mode would emit (here a single
# oversized custom header) exceeds the Zyte API proxy's ~100 KB limit, so proxy
# mode would fail with 431 /request/header-size.
LARGE_HEADER_PARAMS = {
    "url": "https://example.com",
    "httpResponseBody": True,
    "customHttpRequestHeaders": [{"name": "X-Big", "value": "a" * (100 * 1024)}],
}


def test_resolve_auto_transport_compatible_large_headers():
    # The HTTP API carries the same data in the body, so use it to dodge the 431.
    request = Request("https://example.com")
    assert _resolve_auto_transport(request, LARGE_HEADER_PARAMS, "zyte") == "http"


def test_resolve_auto_transport_compatible_large_headers_unknown_header():
    # An unknown Zyte-* header cannot be reproduced over the HTTP API, so the
    # request stays in proxy mode even though it will hit the header-size limit.
    request = Request("https://example.com", headers={b"Zyte-Future": b"1"})
    assert _resolve_auto_transport(request, LARGE_HEADER_PARAMS, "zyte") == "proxy"


# ----------------------------------------------------------------------------
# _header_is_decisive
# ----------------------------------------------------------------------------


def test_header_is_decisive_true():
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert _header_is_decisive(request, settings(), True) is True


def test_header_is_decisive_disabled():
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert _header_is_decisive(request, settings(), False) is False


def test_header_is_decisive_no_headers():
    request = Request("https://example.com")
    assert _header_is_decisive(request, settings(), True) is False


def test_header_is_decisive_with_automap_meta():
    request = Request(
        "https://example.com",
        headers={b"Zyte-Device": b"mobile"},
        meta={"zyte_api_automap": True},
    )
    assert _header_is_decisive(request, settings(), True) is False


def test_header_is_decisive_transparent_mode():
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert (
        _header_is_decisive(request, settings(ZYTE_API_TRANSPARENT_MODE=True), True)
        is False
    )


# ----------------------------------------------------------------------------
# _resolve_transport
# ----------------------------------------------------------------------------


def resolve(request, api_params, *, auth="zyte", header_enabled=True, **kw):
    return _resolve_transport(request, api_params, settings(**kw), auth, header_enabled)


def test_resolve_transport_explicit_proxy():
    request = Request("https://example.com", meta={"zyte_api_transport": "proxy"})
    assert resolve(request, COMPATIBLE_PARAMS) == ("proxy", "proxy", None, [])


def test_resolve_transport_explicit_http():
    request = Request("https://example.com", meta={"zyte_api_transport": "http"})
    # Explicit http short-circuits before computing proxy incompatibility.
    assert resolve(request, COMPATIBLE_PARAMS) == ("http", "http", None, [])


def test_resolve_transport_auto_compatible_explicit():
    request = Request("https://example.com", meta={"zyte_api_transport": "auto"})
    assert resolve(request, COMPATIBLE_PARAMS) == ("auto", "proxy", None, [])


def test_resolve_transport_auto_compatible_not_explicit():
    # Eligible, but experimental gating sends it through HTTP with a warning.
    request = Request("https://example.com", meta={"zyte_api_automap": True})
    assert resolve(request, COMPATIBLE_PARAMS) == ("auto", "http", "transport", [])


def test_resolve_transport_auto_header_decisive_not_explicit():
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert resolve(request, COMPATIBLE_PARAMS) == ("auto", "http", "header", [])


def test_resolve_transport_auto_incompatible():
    request = Request("https://example.com", meta={"zyte_api_automap": True})
    # Incompatible params are surfaced for the handler even when the request
    # falls back to the HTTP API.
    assert resolve(request, INCOMPATIBLE_PARAMS) == ("auto", "http", None, ["product"])


def test_resolve_transport_non_zyte_auth():
    request = Request("https://example.com", meta={"zyte_api_automap": True})
    assert resolve(request, COMPATIBLE_PARAMS, auth="apikey") == (
        "auto",
        "http",
        None,
        [],
    )


def test_resolve_transport_auto_large_headers_explicit():
    # Explicit auto + proxy-compatible + oversized headers -> HTTP API, no
    # experimental fallback (it is not "eligible for proxy", just too big for it).
    request = Request("https://example.com", meta={"zyte_api_transport": "auto"})
    assert resolve(request, LARGE_HEADER_PARAMS) == ("auto", "http", None, [])


def test_resolve_transport_explicit_proxy_large_headers():
    # Forced proxy mode is left to fail (431) rather than silently downgraded.
    request = Request("https://example.com", meta={"zyte_api_transport": "proxy"})
    assert resolve(request, LARGE_HEADER_PARAMS) == ("proxy", "proxy", None, [])


def test_resolve_transport_unknown_header_stays_proxy():
    request = Request(
        "https://example.com",
        headers={b"Zyte-Future": b"1"},
        meta={"zyte_api_transport": "auto"},
    )
    # Explicit auto + unknown header + incompatible params -> proxy (hard error
    # surfaces later in the handler), with the incompatible params carried along.
    assert resolve(request, INCOMPATIBLE_PARAMS) == ("auto", "proxy", None, ["product"])


# ----------------------------------------------------------------------------
# _smartproxy_enabled
# ----------------------------------------------------------------------------


def test_smartproxy_enabled_setting():
    spider = Spider(name="x")
    assert _smartproxy_enabled(settings(ZYTE_SMARTPROXY_ENABLED=True), spider) is True
    assert _smartproxy_enabled(settings(), spider) is False


def test_smartproxy_enabled_spider_attr_precedence():
    spider = Spider(name="x")
    spider.zyte_smartproxy_enabled = True  # type: ignore[attr-defined]
    assert _smartproxy_enabled(settings(ZYTE_SMARTPROXY_ENABLED=False), spider) is True


# ----------------------------------------------------------------------------
# _ParamParser transport helpers (require a crawler)
# ----------------------------------------------------------------------------


@deferred_f_from_coro_f
async def test_param_parser_header_transport_enabled_default():
    crawler = await get_crawler()
    parser = _ParamParser(crawler)
    assert parser._header_transport_enabled() is True


@deferred_f_from_coro_f
async def test_param_parser_header_transport_enabled_explicit_false():
    crawler = await get_crawler({"ZYTE_API_HEADER_TRANSPORT_ENABLED": False})
    parser = _ParamParser(crawler)
    assert parser._header_transport_enabled() is False


@deferred_f_from_coro_f
async def test_param_parser_header_transport_enabled_smartproxy():
    crawler = await get_crawler({"ZYTE_SMARTPROXY_ENABLED": True})
    parser = _ParamParser(crawler)
    # Defaults to False when scrapy-zyte-smartproxy is enabled.
    assert parser._header_transport_enabled() is False


@deferred_f_from_coro_f
async def test_param_parser_header_transport_enabled_smartproxy_override():
    crawler = await get_crawler(
        {"ZYTE_SMARTPROXY_ENABLED": True, "ZYTE_API_HEADER_TRANSPORT_ENABLED": True}
    )
    parser = _ParamParser(crawler)
    assert parser._header_transport_enabled() is True


@deferred_f_from_coro_f
async def test_param_parser_is_proxy_bound_explicit_proxy():
    crawler = await get_crawler()
    parser = _ParamParser(crawler)
    request = Request("https://example.com", meta={"zyte_api_transport": "proxy"})
    assert parser._is_proxy_bound(request) is True


@deferred_f_from_coro_f
async def test_param_parser_is_proxy_bound_auto_with_headers_explicit():
    crawler = await get_crawler({"ZYTE_API_HEADER_TRANSPORT_ENABLED": True})
    parser = _ParamParser(crawler)
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    assert parser._is_proxy_bound(request) is True


@deferred_f_from_coro_f
async def test_param_parser_is_proxy_bound_auto_with_headers_not_explicit():
    crawler = await get_crawler()
    parser = _ParamParser(crawler)
    request = Request("https://example.com", headers={b"Zyte-Device": b"mobile"})
    # Header transport defaults to enabled but is not "explicit" gating-wise.
    assert parser._is_proxy_bound(request) is False


@deferred_f_from_coro_f
async def test_param_parser_is_proxy_bound_auto_no_headers():
    crawler = await get_crawler({"ZYTE_API_TRANSPORT": "auto"})
    parser = _ParamParser(crawler)
    request = Request("https://example.com", meta={"zyte_api_automap": True})
    assert parser._is_proxy_bound(request) is False


# ----------------------------------------------------------------------------
# _ParamParser._meta_key
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("meta", "settings_kwargs", "headers", "expected"),
    [
        # Raw zyte_api parameters take precedence over automatic mapping.
        ({"zyte_api": {"browserHtml": True}}, {}, {}, "zyte_api"),
        ({"zyte_api": True}, {}, {}, "zyte_api"),
        ({"zyte_api": {}}, {}, {}, "zyte_api"),
        # zyte_api set to False (or a deprecated falsy value) is not raw.
        ({"zyte_api": False}, {}, {}, None),
        ({"zyte_api": None}, {}, {}, None),
        # Explicit automatic mapping.
        ({"zyte_api_automap": {"browserHtml": True}}, {}, {}, "zyte_api_automap"),
        ({"zyte_api_automap": True}, {}, {}, "zyte_api_automap"),
        # An explicit automap opt-out means the request does not use Zyte API.
        ({"zyte_api_automap": False}, {}, {}, None),
        # No Zyte API metadata and no opt-in: not routed through Zyte API.
        ({}, {}, {}, None),
        # Transparent mode opts bare requests into automatic mapping, …
        ({}, {"ZYTE_API_TRANSPARENT_MODE": True}, {}, "zyte_api_automap"),
        # … but an explicit automap opt-out still wins.
        ({"zyte_api_automap": False}, {"ZYTE_API_TRANSPARENT_MODE": True}, {}, None),
        # The zyte_api_transport metadata key opts bare requests into automap, …
        ({"zyte_api_transport": "auto"}, {}, {}, "zyte_api_automap"),
        # … and here too the explicit automap opt-out wins.
        ({"zyte_api_transport": "auto", "zyte_api_automap": False}, {}, {}, None),
        # Proxy-mode headers opt bare requests into automatic mapping when header
        # transport is enabled, and do not when it is disabled.
        (
            {},
            {"ZYTE_API_HEADER_TRANSPORT_ENABLED": True},
            {b"Zyte-Device": b"mobile"},
            "zyte_api_automap",
        ),
        (
            {},
            {"ZYTE_API_HEADER_TRANSPORT_ENABLED": False},
            {b"Zyte-Device": b"mobile"},
            None,
        ),
    ],
)
@deferred_f_from_coro_f
async def test_param_parser_meta_key(meta, settings_kwargs, headers, expected):
    crawler = await get_crawler(settings_kwargs)
    parser = _ParamParser(crawler)
    request = Request("https://example.com", meta=meta, headers=headers)
    assert parser._meta_key(request) == expected


# ----------------------------------------------------------------------------
# _ParamParser.parse: proxy header pass-through (final / force_http)
# ----------------------------------------------------------------------------


@deferred_f_from_coro_f
async def test_parse_final_proxy_leaves_headers_unmapped(caplog):
    crawler = await get_crawler({"ZYTE_API_TRANSPORT": "proxy"})
    parser = _ParamParser(crawler)
    request = Request(
        "https://example.com",
        headers={b"Zyte-Device": b"mobile"},
        meta={"zyte_api_automap": True},
    )
    with caplog.at_level("WARNING"):
        params = parser.parse(request, final=True)
    # The proxy-mode header is NOT mapped to a parameter; it is left in
    # Request.headers for pass-through to the proxy endpoint.
    assert "device" not in params
    assert request.headers.get(b"Zyte-Device") == b"mobile"
    assert "has been dropped" not in caplog.text


@deferred_f_from_coro_f
async def test_parse_nonfinal_proxy_maps_headers_silently(caplog):
    crawler = await get_crawler({"ZYTE_API_TRANSPORT": "proxy"})
    parser = _ParamParser(crawler)
    request = Request(
        "https://example.com",
        headers={b"Zyte-Device": b"mobile"},
        meta={"zyte_api_automap": True},
    )
    with caplog.at_level("WARNING"):
        params = parser.parse(request, final=False)
    # Non-final (e.g. fingerprinting) parse maps the header for determinism,
    # but suppresses the misleading "dropped" warning.
    assert params["device"] == "mobile"
    assert "has been dropped" not in caplog.text


@deferred_f_from_coro_f
async def test_parse_force_http_maps_headers_with_warning(caplog):
    crawler = await get_crawler({"ZYTE_API_TRANSPORT": "proxy"})
    parser = _ParamParser(crawler)
    request = Request(
        "https://example.com",
        headers={b"Zyte-Device": b"mobile"},
        meta={"zyte_api_automap": True},
    )
    with caplog.at_level("WARNING"):
        params = parser.parse(request, final=True, force_http=True)
    # force_http maps Zyte-* headers to HTTP API parameters and warns.
    assert params["device"] == "mobile"
    assert "has been dropped" in caplog.text
