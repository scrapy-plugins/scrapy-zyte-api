import asyncio
import inspect
from asyncio import iscoroutine
from collections import defaultdict
from copy import copy
from functools import partial
from http.cookiejar import Cookie
from inspect import isclass
from typing import Any, Dict, Type, cast
from unittest import mock

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider, signals
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.downloadermiddlewares.httpcompression import ACCEPTED_ENCODINGS
from scrapy.exceptions import CloseSpider
from scrapy.http import Response, TextResponse
from scrapy.http.cookies import CookieJar
from scrapy.settings.default_settings import DEFAULT_REQUEST_HEADERS
from scrapy.settings.default_settings import USER_AGENT as DEFAULT_USER_AGENT
from twisted.internet.defer import Deferred
from zyte_api.aio.errors import RequestError

from scrapy_zyte_api._cookies import _get_cookie_jar
from scrapy_zyte_api._params import _EXTRACT_KEYS, ANY_VALUE
from scrapy_zyte_api.handler import _ParamParser
from scrapy_zyte_api.responses import _process_response

from . import (
    DEFAULT_CLIENT_CONCURRENCY,
    SETTINGS,
    SETTINGS_T,
    get_crawler,
    get_download_handler,
    get_downloader_middleware,
    set_env,
)
from .mockserver import DelayedResource, MockServer, produce_request_response

# Pick one of the automatic extraction keys for testing purposes.
EXTRACT_KEYS_ITER = iter(_EXTRACT_KEYS)
EXTRACT_KEY = next(EXTRACT_KEYS_ITER)
EXTRACT_KEY_2 = next(EXTRACT_KEYS_ITER)

DEFAULT_ACCEPT_ENCODING = ", ".join(
    encoding.decode() for encoding in ACCEPTED_ENCODINGS
)


def sort_dict_list(dict_list):
    return sorted(dict_list, key=lambda i: sorted(i.items()))


@pytest.mark.parametrize(
    "meta",
    [
        {
            "httpResponseBody": True,
            "customHttpRequestHeaders": [
                {"name": "Accept", "value": "application/octet-stream"}
            ],
        },
        pytest.param(
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "Accept", "value": "application/octet-stream"}
                ],
            },
            marks=pytest.mark.xfail(
                reason="https://github.com/scrapy-plugins/scrapy-zyte-api/issues/47",
                strict=True,
            ),
        ),
    ],
)
@ensureDeferred
async def test_response_binary(meta: Dict[str, Dict[str, Any]], mockserver):
    """Test that binary (i.e. non-text) responses from Zyte API are
    successfully mapped to a subclass of Response that is not also a subclass
    of TextResponse.

    Whether response headers are retrieved or not should have no impact on the
    outcome if the body is unequivocally binary.
    """
    req, resp = await produce_request_response(mockserver, {"zyte_api": meta})
    assert isinstance(resp, Response)
    assert not isinstance(resp, TextResponse)
    assert resp.request is req
    assert resp.url == req.url
    assert resp.status == 200
    assert "zyte-api" in resp.flags
    assert resp.body == b"\x00"


@ensureDeferred
@pytest.mark.parametrize(
    "meta",
    [
        {"browserHtml": True, "httpResponseHeaders": True},
        {"browserHtml": True},
        {"httpResponseBody": True, "httpResponseHeaders": True},
        pytest.param(
            {"httpResponseBody": True},
            marks=pytest.mark.xfail(
                reason="https://github.com/scrapy-plugins/scrapy-zyte-api/issues/47",
                strict=True,
            ),
        ),
    ],
)
async def test_response_html(meta: Dict[str, Dict[str, Any]], mockserver):
    """Test that HTML responses from Zyte API are successfully mapped to a
    subclass of TextResponse.

    Whether response headers are retrieved or not should have no impact on the
    outcome if the body is unequivocally HTML.
    """
    req, resp = await produce_request_response(mockserver, {"zyte_api": meta})
    assert isinstance(resp, TextResponse)
    assert resp.request is req
    assert resp.url == req.url
    assert resp.status == 200
    assert "zyte-api" in resp.flags
    assert resp.body == b"<html><body>Hello<h1>World!</h1></body></html>"
    assert resp.text == "<html><body>Hello<h1>World!</h1></body></html>"
    assert resp.css("h1 ::text").get() == "World!"
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    if meta.get("httpResponseHeaders", False) is True:
        assert resp.headers == {b"Test_Header": [b"test_value"]}
    else:
        assert not resp.headers


UNSET = object()


@ensureDeferred
@pytest.mark.parametrize(
    "setting,enabled",
    [
        (UNSET, True),
        (True, True),
        (False, False),
    ],
)
async def test_enabled(setting, enabled, mockserver):
    settings = {}
    if setting is not UNSET:
        settings["ZYTE_API_ENABLED"] = setting
    async with mockserver.make_handler(settings) as handler:
        if enabled:
            assert handler is not None
        else:
            assert handler is None


@pytest.mark.parametrize("zyte_api", [True, False])
@ensureDeferred
async def test_coro_handling(zyte_api: bool, mockserver):
    """ScrapyZyteAPIDownloadHandler.download_request must return a deferred
    both when using Zyte API and when using the regular downloader logic."""
    settings = {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True}}
    async with mockserver.make_handler(settings) as handler:
        req = Request(
            # this should really be a URL to a website, not to the API server,
            # but API server URL works ok
            mockserver.urljoin("/"),
            meta={"zyte_api": zyte_api},
        )
        dfd = handler.download_request(req, Spider("test"))
        assert not iscoroutine(dfd)
        assert isinstance(dfd, Deferred)
        await dfd


@ensureDeferred
@pytest.mark.parametrize(
    "meta, exception_type, exception_text",
    [
        (
            {"zyte_api": {"echoData": Request("http://test.com")}},
            TypeError,
            (
                "Got an error when processing Zyte API request "
                "(http://example.com): Object of type Request is not JSON "
                "serializable"
            ),
        ),
        (
            {"zyte_api": {"browserHtml": True, "httpResponseBody": True}},
            RequestError,
            (
                "Got Zyte API error (status=422, type='/request/unprocessable'"
                ", request_id='abcd1234') while processing URL "
                "(http://example.com): Incompatible parameters were found in "
                "the request."
            ),
        ),
    ],
)
async def test_exceptions(
    caplog: LogCaptureFixture,
    meta: Dict[str, Dict[str, Any]],
    exception_type: Type[Exception],
    exception_text: str,
    mockserver,
):
    caplog.set_level("DEBUG")
    async with mockserver.make_handler() as handler:
        req = Request("http://example.com", method="POST", meta=meta)
        with pytest.raises(exception_type):
            await handler.download_request(req, None)
        assert exception_text in caplog.text


@ensureDeferred
async def test_higher_concurrency():
    """Make sure that CONCURRENT_REQUESTS and CONCURRENT_REQUESTS_PER_DOMAIN
    have an effect on Zyte API requests."""
    # Send DEFAULT_CLIENT_CONCURRENCY + 1 requests, the last one taking less
    # time than the rest, and ensure that the first response comes from the
    # last request, verifying that a concurrency ≥ DEFAULT_CLIENT_CONCURRENCY
    # + 1 has been reached.
    concurrency = DEFAULT_CLIENT_CONCURRENCY + 1
    response_indexes = []
    expected_first_index = concurrency - 1
    fast_seconds = 0.001
    slow_seconds = 0.2

    with MockServer(DelayedResource) as server:

        class TestSpider(Spider):
            name = "test_spider"

            def start_requests(self):
                for index in range(concurrency):
                    yield Request(
                        "https://example.com",
                        meta={
                            "index": index,
                            "zyte_api": {
                                "browserHtml": True,
                                "delay": (
                                    fast_seconds
                                    if index == expected_first_index
                                    else slow_seconds
                                ),
                            },
                        },
                        dont_filter=True,
                    )

            async def parse(self, response):
                response_indexes.append(response.meta["index"])
                raise CloseSpider

        crawler = await get_crawler(
            {
                "CONCURRENT_REQUESTS": concurrency,
                "CONCURRENT_REQUESTS_PER_DOMAIN": concurrency,
                "ZYTE_API_URL": server.urljoin("/"),
            },
            TestSpider,
            setup_engine=False,
        )
        await crawler.crawl()

    assert response_indexes[0] == expected_first_index


AUTOMAP_PARAMS: Dict[str, Any] = {}
BROWSER_HEADERS = {b"referer": "referer"}
DEFAULT_PARAMS: Dict[str, Any] = {}
TRANSPARENT_MODE = False
SKIP_HEADERS = {
    b"cookie": ANY_VALUE,
}
JOB_ID = None
COOKIES_ENABLED = False
MAX_COOKIES = 100
GET_API_PARAMS_KWARGS = {
    "default_params": DEFAULT_PARAMS,
    "transparent_mode": TRANSPARENT_MODE,
    "automap_params": AUTOMAP_PARAMS,
    "http_skip_headers": SKIP_HEADERS,
    "browser_headers": BROWSER_HEADERS,
    "job_id": JOB_ID,
    "cookies_enabled": COOKIES_ENABLED,
    "max_cookies": MAX_COOKIES,
}


@ensureDeferred
async def test_params_parser_input_default(mockserver):
    async with mockserver.make_handler() as handler:
        for key in GET_API_PARAMS_KWARGS:
            actual = getattr(handler._param_parser, f"_{key}")
            expected = GET_API_PARAMS_KWARGS[key]
            assert actual == expected, key


@ensureDeferred
async def test_param_parser_input_custom(mockserver):
    settings = {
        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
        "ZYTE_API_AUTOMAP_PARAMS": {"c": "d"},
        "ZYTE_API_BROWSER_HEADERS": {"B": "b"},
        "ZYTE_API_DEFAULT_PARAMS": {"a": "b"},
        "ZYTE_API_MAX_COOKIES": 1,
        "ZYTE_API_SKIP_HEADERS": {"A"},
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    async with mockserver.make_handler(settings) as handler:
        parser = handler._param_parser
        assert parser._automap_params == {"c": "d"}
        assert parser._browser_headers == {b"b": "b"}
        assert parser._cookies_enabled is True
        assert parser._default_params == {"a": "b"}
        assert parser._max_cookies == 1
        assert parser._http_skip_headers == {
            b"a": ANY_VALUE,
        }
        assert parser._transparent_mode is True


@ensureDeferred
@pytest.mark.parametrize(
    "output,uses_zyte_api",
    [
        (None, False),
        ({}, True),
        ({"a": "b"}, True),
    ],
)
async def test_param_parser_output_side_effects(output, uses_zyte_api, mockserver):
    """If _get_api_params returns None, requests go outside Zyte API, but if it
    returns a dictionary, even if empty, requests go through Zyte API."""
    request = Request(url=mockserver.urljoin("/"))
    async with mockserver.make_handler() as handler:
        handler._param_parser = mock.Mock()
        handler._param_parser.parse = mock.Mock(return_value=output)
        handler._download_request = mock.AsyncMock(side_effect=RuntimeError)
        handler._fallback_handler = mock.Mock()
        handler._fallback_handler.download_request = mock.AsyncMock(
            side_effect=RuntimeError
        )
        with pytest.raises(RuntimeError):
            await handler.download_request(request, None)
    if uses_zyte_api:
        handler._download_request.assert_called()
    else:
        handler._fallback_handler.download_request.assert_called()


DEFAULT_AUTOMAP_PARAMS: Dict[str, Any] = {
    "httpResponseBody": True,
    "httpResponseHeaders": True,
}


@pytest.mark.parametrize(
    "setting,meta,expected",
    [
        (False, None, None),
        (False, {}, None),
        (False, {"a": "b"}, None),
        (False, {"zyte_api": False}, None),
        (False, {"zyte_api": True}, {}),
        (False, {"zyte_api": {}}, {}),
        (False, {"zyte_api": {"a": "b"}}, {"a": "b"}),
        (False, {"zyte_api_automap": False}, None),
        (False, {"zyte_api_automap": True}, DEFAULT_AUTOMAP_PARAMS),
        (False, {"zyte_api_automap": {}}, DEFAULT_AUTOMAP_PARAMS),
        (False, {"zyte_api_automap": {"a": "b"}}, {**DEFAULT_AUTOMAP_PARAMS, "a": "b"}),
        (False, {"zyte_api": False, "zyte_api_automap": False}, None),
        (False, {"zyte_api": False, "zyte_api_automap": True}, DEFAULT_AUTOMAP_PARAMS),
        (False, {"zyte_api": False, "zyte_api_automap": {}}, DEFAULT_AUTOMAP_PARAMS),
        (
            False,
            {"zyte_api": False, "zyte_api_automap": {"a": "b"}},
            {**DEFAULT_AUTOMAP_PARAMS, "a": "b"},
        ),
        (False, {"zyte_api": True, "zyte_api_automap": False}, {}),
        (False, {"zyte_api": True, "zyte_api_automap": True}, ValueError),
        (False, {"zyte_api": True, "zyte_api_automap": {}}, ValueError),
        (False, {"zyte_api": True, "zyte_api_automap": {"a": "b"}}, ValueError),
        (False, {"zyte_api": {}, "zyte_api_automap": False}, {}),
        (False, {"zyte_api": {}, "zyte_api_automap": True}, ValueError),
        (False, {"zyte_api": {}, "zyte_api_automap": {}}, ValueError),
        (False, {"zyte_api": {}, "zyte_api_automap": {"a": "b"}}, ValueError),
        (False, {"zyte_api": {"a": "b"}, "zyte_api_automap": False}, {"a": "b"}),
        (False, {"zyte_api": {"a": "b"}, "zyte_api_automap": True}, ValueError),
        (False, {"zyte_api": {"a": "b"}, "zyte_api_automap": {}}, ValueError),
        (False, {"zyte_api": {"a": "b"}, "zyte_api_automap": {"a": "b"}}, ValueError),
        (True, None, DEFAULT_AUTOMAP_PARAMS),
        (True, {}, DEFAULT_AUTOMAP_PARAMS),
        (True, {"a": "b"}, DEFAULT_AUTOMAP_PARAMS),
        (True, {"zyte_api": False}, DEFAULT_AUTOMAP_PARAMS),
        (True, {"zyte_api": True}, {}),
        (True, {"zyte_api": {}}, {}),
        (True, {"zyte_api": {"a": "b"}}, {"a": "b"}),
        (True, {"zyte_api_automap": False}, None),
        (True, {"zyte_api_automap": True}, DEFAULT_AUTOMAP_PARAMS),
        (True, {"zyte_api_automap": {}}, DEFAULT_AUTOMAP_PARAMS),
        (True, {"zyte_api_automap": {"a": "b"}}, {**DEFAULT_AUTOMAP_PARAMS, "a": "b"}),
        (True, {"zyte_api": False, "zyte_api_automap": False}, None),
        (True, {"zyte_api": False, "zyte_api_automap": True}, DEFAULT_AUTOMAP_PARAMS),
        (True, {"zyte_api": False, "zyte_api_automap": {}}, DEFAULT_AUTOMAP_PARAMS),
        (
            True,
            {"zyte_api": False, "zyte_api_automap": {"a": "b"}},
            {**DEFAULT_AUTOMAP_PARAMS, "a": "b"},
        ),
        (True, {"zyte_api": True, "zyte_api_automap": False}, {}),
        (True, {"zyte_api": True, "zyte_api_automap": True}, ValueError),
        (True, {"zyte_api": True, "zyte_api_automap": {}}, ValueError),
        (True, {"zyte_api": True, "zyte_api_automap": {"a": "b"}}, ValueError),
        (True, {"zyte_api": {}, "zyte_api_automap": False}, {}),
        (True, {"zyte_api": {}, "zyte_api_automap": True}, ValueError),
        (True, {"zyte_api": {}, "zyte_api_automap": {}}, ValueError),
        (True, {"zyte_api": {}, "zyte_api_automap": {"a": "b"}}, ValueError),
        (True, {"zyte_api": {"a": "b"}, "zyte_api_automap": False}, {"a": "b"}),
        (True, {"zyte_api": {"a": "b"}, "zyte_api_automap": True}, ValueError),
        (True, {"zyte_api": {"a": "b"}, "zyte_api_automap": {}}, ValueError),
        (True, {"zyte_api": {"a": "b"}, "zyte_api_automap": {"a": "b"}}, ValueError),
    ],
)
@ensureDeferred
async def test_transparent_mode_toggling(setting, meta, expected):
    """Test how the value of the ``ZYTE_API_TRANSPARENT_MODE`` setting
    (*setting*) in combination with request metadata (*meta*) determines what
    Zyte API parameters are used (*expected*).

    Note that :func:`test_param_parser_output_side_effects` already tests how
    *expected* affects whether the request is sent through Zyte API or not,
    and :func:`test_param_parser_input_custom` tests how the
    ``ZYTE_API_TRANSPARENT_MODE`` setting is mapped to the corresponding
    :func:`~scrapy_zyte_api.handler._get_api_params` parameter.
    """
    request = Request(url="https://example.com", meta=meta)
    settings = {"ZYTE_API_TRANSPARENT_MODE": setting}
    crawler = await get_crawler(settings)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    func = partial(param_parser.parse, request)
    if isclass(expected):
        with pytest.raises(expected):
            func()
    else:
        api_params = func()
        if api_params is not None:
            api_params.pop("url")
        assert api_params == expected


@pytest.mark.parametrize("meta", [None, 0, "", b"", [], ()])
@ensureDeferred
async def test_api_disabling_deprecated(meta):
    """Test how undocumented falsy values of the ``zyte_api`` request metadata
    key (*meta*) can be used to disable the use of Zyte API, but trigger a
    deprecation warning asking to replace them with False."""
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = meta
    crawler = await get_crawler()
    param_parser = _ParamParser(crawler)
    with pytest.warns(DeprecationWarning, match=r".* Use False instead\.$"):
        api_params = param_parser.parse(request)
    assert api_params is None


@pytest.mark.parametrize("key", ["zyte_api", "zyte_api_automap"])
@pytest.mark.parametrize("value", [1, ["a", "b"]])
@ensureDeferred
async def test_bad_meta_type(key, value):
    """Test how undocumented truthy values (*value*) for the ``zyte_api`` and
    ``zyte_api_automap`` request metadata keys (*key*) trigger a
    :exc:`ValueError` exception."""
    request = Request(url="https://example.com", meta={key: value})
    crawler = await get_crawler()
    param_parser = _ParamParser(crawler)
    with pytest.raises(ValueError):
        param_parser.parse(request)


@pytest.mark.parametrize("meta", ["zyte_api", "zyte_api_automap"])
@ensureDeferred
async def test_job_id(meta, mockserver):
    """Test how the value of the ``SHUB_JOBKEY`` environment variable is
    included as ``jobId`` among the parameters sent to Zyte API, both with
    manually-defined parameters and with automatically-mapped parameters.

    Note that :func:`test_param_parser_input_custom` already tests how the
    ``JOB`` setting is mapped to the corresponding
    :func:`~scrapy_zyte_api.handler._get_api_params` parameter.
    """
    request = Request(url="https://example.com", meta={meta: True})
    with set_env(SHUB_JOBKEY="1/2/3"):
        crawler = await get_crawler()
        handler = get_download_handler(crawler, "https")
        param_parser = handler._param_parser
        api_params = param_parser.parse(request)
    assert api_params["jobId"] == "1/2/3"


@ensureDeferred
async def test_default_params_none(mockserver, caplog):
    """Test how setting a value to ``None`` in the dictionary of the
    ZYTE_API_DEFAULT_PARAMS and ZYTE_API_AUTOMAP_PARAMS settings causes a
    warning, because that is not expected to be a valid value.

    Note that ``None`` is however a valid value for parameters defined in the
    ``zyte_api`` and ``zyte_api_automap`` request metadata keys. It can be used
    to unset parameters set in those settings for a specific request.

    Also note that :func:`test_param_parser_input_custom` already tests how
    the settings are mapped to the corresponding
    :func:`~scrapy_zyte_api.handler._get_api_params` parameter.
    """
    settings = {
        "ZYTE_API_DEFAULT_PARAMS": {"a": None, "b": "c"},
        "ZYTE_API_AUTOMAP_PARAMS": {"d": None, "e": "f"},
    }
    with caplog.at_level("WARNING"):
        async with mockserver.make_handler(settings) as handler:
            assert handler._param_parser._automap_params == {"e": "f"}
            assert handler._param_parser._default_params == {"b": "c"}
    assert "Parameter 'a' in the ZYTE_API_DEFAULT_PARAMS setting is None" in caplog.text
    assert "Parameter 'd' in the ZYTE_API_AUTOMAP_PARAMS setting is None" in caplog.text


@pytest.mark.parametrize(
    "setting,meta,expected,warnings",
    [
        ({}, {}, {}, []),
        ({}, {"b": 2}, {"b": 2}, []),
        ({}, {"b": None}, {}, ["parameter b is None"]),
        ({"a": 1}, {}, {"a": 1}, []),
        ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}, []),
        ({"a": 1}, {"b": None}, {"a": 1}, ["parameter b is None"]),
        ({"a": 1}, {"a": 2}, {"a": 2}, []),
        ({"a": 1}, {"a": None}, {}, []),
        ({"a": {"b": 1}}, {}, {"a": {"b": 1}}, []),
        ({"a": {"b": 1}}, {"a": {"c": 1}}, {"a": {"b": 1, "c": 1}}, []),
        (
            {"a": {"b": 1}},
            {"a": {"c": None}},
            {"a": {"b": 1}},
            ["parameter a.c is None"],
        ),
        ({"a": {"b": 1}}, {"a": {"b": 2}}, {"a": {"b": 2}}, []),
        ({"a": {"b": 1}}, {"a": {"b": None}}, {}, []),
        ({"a": {"b": 1, "c": 1}}, {"a": {"b": None}}, {"a": {"c": 1}}, []),
    ],
)
@pytest.mark.parametrize(
    "setting_key,meta_key,ignore_keys",
    [
        ("ZYTE_API_DEFAULT_PARAMS", "zyte_api", set()),
        (
            "ZYTE_API_AUTOMAP_PARAMS",
            "zyte_api_automap",
            set(DEFAULT_AUTOMAP_PARAMS),
        ),
    ],
)
@ensureDeferred
async def test_default_params_merging(
    setting_key, meta_key, ignore_keys, setting, meta, expected, warnings, caplog
):
    """Test how Zyte API parameters defined in the *arg_key* _get_api_params
    parameter and those defined in the *meta_key* request metadata key are
    combined.

    Request metadata takes precedence. Also, ``None`` values in request
    metadata can be used to unset parameters defined in the setting. Request
    metadata ``None`` values for keys that do not exist in the setting cause a
    warning.

    This test also makes sure that, when `None` is used to unset a parameter,
    the original request metadata key value is not modified.
    """
    request = Request(url="https://example.com")
    request.meta[meta_key] = meta
    crawler = await get_crawler({setting_key: setting})
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    caplog.clear()
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    for key in ignore_keys:
        api_params.pop(key)
    api_params.pop("url")
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records


@pytest.mark.parametrize(
    "setting,meta",
    [
        # append
        (
            {"a": "b"},
            {"b": "c"},
        ),
        # overwrite
        (
            {"a": "b"},
            {"a": "c"},
        ),
        # drop
        (
            {"a": "b"},
            {"a": None},
        ),
    ],
)
@pytest.mark.parametrize(
    "setting_key,meta_key",
    [
        ("ZYTE_API_DEFAULT_PARAMS", "zyte_api"),
        (
            "ZYTE_API_AUTOMAP_PARAMS",
            "zyte_api_automap",
        ),
    ],
)
@ensureDeferred
async def test_default_params_immutability(setting_key, meta_key, setting, meta):
    """Make sure that the merging of Zyte API parameters from the *arg_key*
    _get_api_params parameter with those from the *meta_key* request metadata
    key does not affect the contents of the setting for later requests."""
    request = Request(url="https://example.com")
    request.meta[meta_key] = meta
    default_params = copy(setting)
    crawler = await get_crawler({setting_key: setting})
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    param_parser.parse(request)
    assert default_params == setting


async def _test_automap(
    settings, request_kwargs, meta, expected, warnings, caplog, cookie_jar=None
):
    request = Request(url="https://example.com", **request_kwargs)
    request.meta["zyte_api_automap"] = meta
    settings = {**settings, "ZYTE_API_TRANSPARENT_MODE": True}
    crawler = await get_crawler(settings)
    await _process_request(crawler, request, is_start_request=True)
    if "cookies" in request_kwargs:
        try:
            cookie_middleware = get_downloader_middleware(crawler, CookiesMiddleware)
        except ValueError:
            pass
        else:
            if cookie_jar:
                _cookie_jar = _get_cookie_jar(request, cookie_middleware.jars)
                for cookie in cookie_jar:
                    _cookie = Cookie(
                        version=1,
                        name=cookie["name"],
                        value=cookie["value"],
                        port=None,
                        port_specified=False,
                        domain=cookie.get("domain"),
                        domain_specified="domain" in cookie,
                        domain_initial_dot=cookie.get("domain", "").startswith("."),
                        path=cookie.get("path", "/"),
                        path_specified="path" in cookie,
                        secure=cookie.get("secure", False),
                        expires=cookie.get("expires", None),
                        discard=False,
                        comment=None,
                        comment_url=None,
                        rest={},
                    )
                    _cookie_jar.set_cookie(_cookie)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    api_params.pop("url")
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        # If no other known main output is specified in meta, httpResponseBody
        # is requested.
        ({}, {"httpResponseBody": True, "httpResponseHeaders": True}, []),
        (
            {"unknownMainOutput": True},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "unknownMainOutput": True,
            },
            [],
        ),
        # httpResponseBody can be explicitly requested in meta, and should be
        # in cases where a binary response is expected, since automatic mapping
        # may stop working for binary responses in the future.
        (
            {"httpResponseBody": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            [],
        ),
        # If other main outputs are specified in meta, httpRequestBody is not
        # set.
        (
            {"browserHtml": True},
            {"browserHtml": True},
            [],
        ),
        (
            {"screenshot": True},
            {"screenshot": True},
            [],
        ),
        (
            {EXTRACT_KEY: True},
            {EXTRACT_KEY: True},
            [],
        ),
        (
            {"browserHtml": True, "screenshot": True},
            {"browserHtml": True, "screenshot": True},
            [],
        ),
        # If no known main output is specified, and httpResponseBody is
        # explicitly set to False, httpResponseBody is unset and no main output
        # is added.
        (
            {"httpResponseBody": False},
            {},
            [],
        ),
        (
            {"httpResponseBody": False, "unknownMainOutput": True},
            {"unknownMainOutput": True},
            [],
        ),
        # We allow httpResponseBody and browserHtml to be both set to True, in
        # case that becomes possible in the future.
        (
            {"httpResponseBody": True, "browserHtml": True},
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # To request httpResponseHeaders on their own, you must disable
        # httpResponseBody.
        (
            {"httpResponseHeaders": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {"httpResponseBody": False, "httpResponseHeaders": True},
            {"httpResponseHeaders": True},
            [],
        ),
    ],
)
@ensureDeferred
async def test_automap_main_outputs(meta, expected, warnings, caplog):
    await _test_automap({}, {}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        # Test cases where httpResponseHeaders is not specifically set to True
        # or False, where it is automatically set to True if httpResponseBody
        # is also True, are covered in test_automap_main_outputs.
        #
        # If httpResponseHeaders is set to True in a scenario where it would
        # not be implicitly set to True, it is passed as such.
        (
            {"httpResponseBody": False, "httpResponseHeaders": True},
            {"httpResponseHeaders": True},
            [],
        ),
        (
            {"browserHtml": True, "httpResponseHeaders": True},
            {"browserHtml": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {"screenshot": True, "httpResponseHeaders": True},
            {"screenshot": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {EXTRACT_KEY: True, "httpResponseHeaders": True},
            {EXTRACT_KEY: True, "httpResponseHeaders": True},
            [],
        ),
        (
            {
                "unknownMainOutput": True,
                "httpResponseBody": False,
                "httpResponseHeaders": True,
            },
            {"unknownMainOutput": True, "httpResponseHeaders": True},
            [],
        ),
        # Setting httpResponseHeaders to True where it would be already True
        # implicitly, i.e. where httpResponseBody is set to True implicitly or
        # explicitly, is OK and should not generate any warning. It is a way
        # to make code future-proof, in case in the future httpResponseHeaders
        # stops being set to True by default in those scenarios.
        (
            {"httpResponseHeaders": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {"httpResponseBody": True, "httpResponseHeaders": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"unknownMainOutput": True, "httpResponseHeaders": True},
            {
                "unknownMainOutput": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # If httpResponseHeaders is set to False, httpResponseHeaders is not
        # defined, even if httpResponseBody is set to True, implicitly or
        # explicitly.
        ({"httpResponseHeaders": False}, {"httpResponseBody": True}, []),
        (
            {"httpResponseBody": True, "httpResponseHeaders": False},
            {"httpResponseBody": True},
            [],
        ),
        (
            {
                "httpResponseBody": True,
                "browserHtml": True,
                "httpResponseHeaders": False,
            },
            {"browserHtml": True, "httpResponseBody": True},
            [],
        ),
        (
            {"unknownMainOutput": True, "httpResponseHeaders": False},
            {"unknownMainOutput": True, "httpResponseBody": True},
            [],
        ),
        # If httpResponseHeaders is unnecessarily set to False where
        # httpResponseBody is set to False implicitly or explicitly,
        # httpResponseHeaders is not defined, and a warning is
        # logged.
        (
            {"httpResponseBody": False, "httpResponseHeaders": False},
            {},
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {"browserHtml": True, "httpResponseHeaders": False},
            {"browserHtml": True},
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {"screenshot": True, "httpResponseHeaders": False},
            {"screenshot": True},
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {EXTRACT_KEY: True, "httpResponseHeaders": False},
            {EXTRACT_KEY: True},
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {
                "unknownMainOutput": True,
                "httpResponseBody": False,
                "httpResponseHeaders": False,
            },
            {"unknownMainOutput": True},
            ["do not need to set httpResponseHeaders to False"],
        ),
    ],
)
@ensureDeferred
async def test_automap_header_output(meta, expected, warnings, caplog):
    await _test_automap({}, {}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "method,meta,expected,warnings",
    [
        # The GET HTTP method is not mapped, since it is the default method.
        (
            "GET",
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # Other HTTP methods, regardless of whether they are supported,
        # unsupported, or unknown, are mapped as httpRequestMethod, letting
        # Zyte API decide whether or not they are allowed.
        *(
            (
                method,
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "httpRequestMethod": method,
                },
                [],
            )
            for method in (
                "POST",
                "PUT",
                "DELETE",
                "OPTIONS",
                "TRACE",
                "PATCH",
                "HEAD",
                "CONNECT",
                "FOO",
            )
        ),
        # If httpRequestMethod is also specified in meta with the same value
        # as Request.method, a warning is logged asking to use only
        # Request.method.
        (
            None,
            {"httpRequestMethod": "GET"},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["Use Request.method"],
        ),
        (
            "POST",
            {"httpRequestMethod": "POST"},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestMethod": "POST",
            },
            ["Use Request.method"],
        ),
        # If httpRequestMethod is also specified in meta with a different value
        # from Request.method, a warning is logged asking to use Request.meta,
        # and the meta value takes precedence.
        (
            "POST",
            {"httpRequestMethod": "GET"},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [
                "Use Request.method",
                "does not match the Zyte API httpRequestMethod",
            ],
        ),
        (
            "POST",
            {"httpRequestMethod": "PUT"},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestMethod": "PUT",
            },
            [
                "Use Request.method",
                "does not match the Zyte API httpRequestMethod",
            ],
        ),
        # If httpResponseBody is not True, implicitly or explicitly,
        # Request.method is still mapped for anything other than GET.
        (
            "POST",
            {"browserHtml": True},
            {
                "browserHtml": True,
                "httpRequestMethod": "POST",
            },
            [],
        ),
        (
            "POST",
            {"screenshot": True},
            {
                "screenshot": True,
                "httpRequestMethod": "POST",
            },
            [],
        ),
        (
            "POST",
            {EXTRACT_KEY: True},
            {
                EXTRACT_KEY: True,
                "httpRequestMethod": "POST",
            },
            [],
        ),
    ],
)
@ensureDeferred
async def test_automap_method(method, meta, expected, warnings, caplog):
    await _test_automap({}, {"method": method}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "headers,meta,expected,warnings",
    [
        # If httpResponseBody is True, implicitly or explicitly,
        # Request.headers are mapped as customHttpRequestHeaders.
        (
            {"Referer": "a"},
            {},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # If browserHtml, screenshot, or automatic extraction properties are
        # True, Request.headers are mapped as requestHeaders.
        (
            {"Referer": "a"},
            {"browserHtml": True},
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"screenshot": True},
            {
                "requestHeaders": {"referer": "a"},
                "screenshot": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {EXTRACT_KEY: True},
            {
                "requestHeaders": {"referer": "a"},
                EXTRACT_KEY: True,
            },
            [],
        ),
        # If both httpResponseBody and browserHtml (or screenshot, or both, or
        # automatic extraction properties) are True, implicitly or explicitly,
        # Request.headers are mapped both as customHttpRequestHeaders and as
        # requestHeaders.
        (
            {"Referer": "a"},
            {"browserHtml": True, "httpResponseBody": True},
            {
                "browserHtml": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"screenshot": True, "httpResponseBody": True},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
                "screenshot": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {EXTRACT_KEY: True, "httpResponseBody": True},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
                EXTRACT_KEY: True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"browserHtml": True, "screenshot": True, "httpResponseBody": True},
            {
                "browserHtml": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
                "screenshot": True,
            },
            [],
        ),
        # If httpResponseBody is True, implicitly or explicitly, and there is
        # no other known main output parameter (browserHtml, screenshot),
        # Request.headers are mapped as customHttpRequestHeaders only.
        #
        # While future main output parameters are likely to use requestHeaders
        # instead, we cannot know if an unknown parameter is a main output
        # parameter or a different type of parameter for httpRequestBody, and
        # what we know for sure is that, at the time of writing, Zyte API does
        # not allow requestHeaders to be combined with httpRequestBody.
        (
            {"Referer": "a"},
            {"unknownMainOutput": True},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "unknownMainOutput": True,
            },
            [],
        ),
        # If no known main output is requested, implicitly or explicitly, we
        # assume that some unknown main output is being requested, and we map
        # Request.headers as requestHeaders because that is the most likely way
        # headers will need to be mapped for a future main output.
        (
            {"Referer": "a"},
            {"httpResponseBody": False},
            {
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"unknownMainOutput": True, "httpResponseBody": False},
            {
                "requestHeaders": {"referer": "a"},
                "unknownMainOutput": True,
            },
            [],
        ),
        # False disables header mapping.
        (
            {"Referer": "a"},
            {"customHttpRequestHeaders": False},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"browserHtml": True, "requestHeaders": False},
            {
                "browserHtml": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "customHttpRequestHeaders": False,
            },
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"browserHtml": True, "httpResponseBody": True, "requestHeaders": False},
            {
                "browserHtml": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "customHttpRequestHeaders": False,
                "requestHeaders": False,
            },
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # True forces header mapping.
        (
            {"Referer": "a"},
            {"requestHeaders": True},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"browserHtml": True, "customHttpRequestHeaders": True},
            {
                "browserHtml": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        # Headers with None as value are not mapped.
        (
            {"Referer": None},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"browserHtml": True, "httpResponseBody": True},
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"screenshot": True},
            {
                "screenshot": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {EXTRACT_KEY: True},
            {
                EXTRACT_KEY: True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"screenshot": True, "httpResponseBody": True},
            {
                "screenshot": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {EXTRACT_KEY: True, "httpResponseBody": True},
            {
                EXTRACT_KEY: True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"unknownMainOutput": True},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "unknownMainOutput": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"unknownMainOutput": True, "httpResponseBody": False},
            {
                "unknownMainOutput": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"httpResponseBody": False},
            {},
            [],
        ),
        # Warn if header parameters are used in meta, even if the values match
        # request headers, and even if there are no request headers to match in
        # the first place. If they do not match, meta takes precedence.
        (
            {"Referer": "a"},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ]
            },
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["Use Request.headers instead"],
        ),
        (
            {"Referer": "a"},
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "a"},
            },
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "a"},
            },
            ["Use Request.headers instead"],
        ),
        (
            {"Referer": "a"},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "b"},
                ]
            },
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "b"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["Use Request.headers instead"],
        ),
        (
            {"Referer": "a"},
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "b"},
            },
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "b"},
            },
            ["Use Request.headers instead"],
        ),
        (
            {},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ]
            },
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["Use Request.headers instead"],
        ),
        (
            {},
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "a"},
            },
            {
                "browserHtml": True,
                "requestHeaders": {"referer": "a"},
            },
            ["Use Request.headers instead"],
        ),
        # If httpRequestBody is True and requestHeaders is defined in meta, or
        # if browserHtml is True and customHttpRequestHeaders is defined in
        # meta, keep the meta parameters and do not issue a warning. There is
        # no need for a warning because the request should get an error
        # response from Zyte API. And if Zyte API were not to send an error
        # response, that would mean the Zyte API has started supporting this
        # scenario, all the more reason not to warn and let the parameters
        # reach Zyte API.
        (
            {},
            {
                "requestHeaders": {"referer": "a"},
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {},
            {
                "browserHtml": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
            },
            {
                "browserHtml": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
            },
            [],
        ),
        # Unsupported headers not present in Scrapy requests by default are
        # dropped with a warning.
        # If all headers are unsupported, the header parameter is not even set.
        (
            {"a": "b"},
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            ["cannot be mapped"],
        ),
        # Headers with an empty string as value are not silently ignored.
        (
            {"a": ""},
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            ["cannot be mapped"],
        ),
        # The Accept, Accept-Encoding, Accept-Language and User-Agent headers,
        # when unsupported (i.e. browser requests), are dropped with a warning
        # if the user set them manually (even if they are set with their
        # default value).
        *(
            (
                headers,
                {"browserHtml": True},
                {
                    "browserHtml": True,
                },
                ["cannot be mapped"],
            )
            for headers in (
                {
                    "Accept": DEFAULT_REQUEST_HEADERS["Accept"],
                },
                {
                    "Accept": "application/json",
                },
                {
                    "Accept-Encoding": DEFAULT_ACCEPT_ENCODING,
                },
                {
                    "Accept-Encoding": "br",
                },
                {
                    "Accept-Language": "uk",
                },
                {
                    "Accept-Language": DEFAULT_REQUEST_HEADERS["Accept-Language"],
                },
                {
                    "User-Agent": DEFAULT_USER_AGENT,
                },
                {
                    "User-Agent": "foo/1.2.3",
                },
            )
        ),
        # The User-Agent header, which Scrapy sets by default, is used for
        # customHttpRequestHeaders if the value comes from a user-defined
        # setting (as opposed to the global default value).
        (
            {"User-Agent": DEFAULT_USER_AGENT},
            {},
            {
                "customHttpRequestHeaders": [
                    {"name": "User-Agent", "value": DEFAULT_USER_AGENT}
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"User-Agent": ""},
            {},
            {
                "customHttpRequestHeaders": [{"name": "User-Agent", "value": ""}],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # Zyte Smart Proxy Manager special header handling.
        (
            {"X-Crawlera-Foo": "Bar"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Client": "Custom client string"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Cookies": "enable"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["To achieve the same behavior with Zyte API, do not set request cookies"],
        ),
        (
            {"X-Crawlera-Cookies": "disable"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["it is the default behavior of Zyte API"],
        ),
        (
            {"X-Crawlera-Cookies": "discard"},
            {},
            {
                "cookieManagement": "discard",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Cookies": "foo"},
            {
                "cookieManagement": "bar",
            },
            {
                "cookieManagement": "bar",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Cookies": "foo"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped to a Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-JobId": "foo"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "jobId": "foo",
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-JobId": "foo"},
            {
                "jobId": "bar",
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "jobId": "bar",
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Max-Retries": "1"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-No-Bancheck": "1"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile": "pass"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Profile": "desktop"},
            {},
            {
                "device": "desktop",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Profile": "mobile"},
            {},
            {
                "device": "mobile",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Profile": "foo"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Profile": "foo"},
            {
                "device": "bar",
            },
            {
                "device": "bar",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Profile-Pass": "foo"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Region": "foo"},
            {},
            {
                "geolocation": "foo",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Region": "foo"},
            {
                "geolocation": "bar",
            },
            {
                "geolocation": "bar",
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Session": "foo"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Timeout": "40000"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Use-Https": "1"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Foo": "Bar"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Client": "Custom client string"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Cookies": "enable"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["To achieve the same behavior with Zyte API, do not set request cookies"],
        ),
        (
            {"X-Crawlera-Cookies": "disable"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["it is the default behavior of Zyte API"],
        ),
        (
            {"X-Crawlera-Cookies": "discard"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
                "cookieManagement": "discard",
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Cookies": "foo"},
            {
                "browserHtml": True,
                "cookieManagement": "bar",
            },
            {
                "browserHtml": True,
                "cookieManagement": "bar",
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Cookies": "foo"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["cannot be mapped to a Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-JobId": "foo"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
                "jobId": "foo",
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-JobId": "foo"},
            {
                "browserHtml": True,
                "jobId": "bar",
            },
            {
                "browserHtml": True,
                "jobId": "bar",
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Max-Retries": "1"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-No-Bancheck": "1"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile": "pass"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile": "desktop"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile": "mobile"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile": "foo"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile": "foo"},
            {
                # Zyte API does not support it, it will trigger a 400 response,
                # but we allow it for forward compatibility, i.e. in case it is
                # supported in the future.
                "device": "bar",
                "browserHtml": True,
            },
            {
                "device": "bar",
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Profile-Pass": "foo"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Region": "foo"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
                "geolocation": "foo",
            },
            ["has been assigned to the matching Zyte API request parameter"],
        ),
        (
            {"X-Crawlera-Region": "foo"},
            {
                "browserHtml": True,
                "geolocation": "bar",
            },
            {
                "browserHtml": True,
                "geolocation": "bar",
            },
            ["has already been defined on the request"],
        ),
        (
            {"X-Crawlera-Session": "foo"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Timeout": "40000"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        (
            {"X-Crawlera-Use-Https": "1"},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
            },
            ["This header has been dropped"],
        ),
        # The extraction source affects header mapping.
        (
            {"Referer": "a"},
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
            },
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
            },
            [],
        ),
        (
            {"Referer": "a"},
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "browserHtml"},
            },
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "browserHtml"},
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        # Only *Options parameters matching enabled extraction outputs are
        # taken into account.
        (
            {"Referer": "a"},
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY_2}Options": {"extractFrom": "httpResponseBody"},
            },
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY_2}Options": {"extractFrom": "httpResponseBody"},
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        # Combining 2 matching extractFrom works as a single one.
        (
            {"Referer": "a"},
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                EXTRACT_KEY_2: True,
                f"{EXTRACT_KEY_2}Options": {"extractFrom": "httpResponseBody"},
            },
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                EXTRACT_KEY_2: True,
                f"{EXTRACT_KEY_2}Options": {"extractFrom": "httpResponseBody"},
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
            },
            [],
        ),
        # Combining 2 conflicting extractFrom causes request headers to be
        # mapped both ways.
        (
            {"Referer": "a"},
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                EXTRACT_KEY_2: True,
            },
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                EXTRACT_KEY_2: True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                EXTRACT_KEY_2: True,
                f"{EXTRACT_KEY_2}Options": {"extractFrom": "browserHtml"},
            },
            {
                EXTRACT_KEY: True,
                f"{EXTRACT_KEY}Options": {"extractFrom": "httpResponseBody"},
                EXTRACT_KEY_2: True,
                f"{EXTRACT_KEY_2}Options": {"extractFrom": "browserHtml"},
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
    ],
)
@ensureDeferred
async def test_automap_headers(headers, meta, expected, warnings, caplog):
    await _test_automap({}, {"headers": headers}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "settings,headers,meta,expected,warnings",
    [
        # You may update the ZYTE_API_SKIP_HEADERS setting to remove
        # headers that the customHttpRequestHeaders parameter starts supporting
        # in the future.
        (
            {
                "ZYTE_API_SKIP_HEADERS": [],
            },
            {
                "User-Agent": "",
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "User-Agent", "value": ""},
                ],
            },
            [],
        ),
        # You may update the ZYTE_API_BROWSER_HEADERS setting to extend support
        # for new fields that the requestHeaders parameter may support in the
        # future.
        (
            {
                "ZYTE_API_BROWSER_HEADERS": {
                    "referer": "referer",
                    "user-agent": "userAgent",
                },
            },
            {"User-Agent": ""},
            {"browserHtml": True},
            {
                "browserHtml": True,
                "requestHeaders": {"userAgent": ""},
            },
            [],
        ),
    ],
)
@ensureDeferred
async def test_automap_header_settings(
    settings, headers, meta, expected, warnings, caplog
):
    await _test_automap(
        settings, {"headers": headers}, meta, expected, warnings, caplog
    )


REQUEST_INPUT_COOKIES_EMPTY: Dict[str, str] = {}
REQUEST_INPUT_COOKIES_MINIMAL_DICT = {"a": "b"}
REQUEST_INPUT_COOKIES_MINIMAL_LIST = [{"name": "a", "value": "b"}]
REQUEST_INPUT_COOKIES_MAXIMAL = [
    {"name": "c", "value": "d", "domain": "example.com", "path": "/"}
]
REQUEST_OUTPUT_COOKIES_MINIMAL = [{"name": "a", "value": "b", "domain": "example.com"}]
REQUEST_OUTPUT_COOKIES_MAXIMAL = [
    {"name": "c", "value": "d", "domain": ".example.com", "path": "/"}
]


@pytest.mark.parametrize(
    "settings,cookies,meta,params,expected,warnings,cookie_jar",
    [
        # Cookies, both for requests and for responses, are enabled based on
        # both ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED (default: False) and
        # COOKIES_ENABLED (default: True).
        *(
            (
                settings,
                input_cookies,
                {},
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                },
                setup_warnings
                or (
                    run_time_warnings
                    if cast(Dict, settings).get("COOKIES_ENABLED", True)
                    else []
                ),
                [],
            )
            for input_cookies, run_time_warnings in (
                (
                    REQUEST_INPUT_COOKIES_EMPTY,
                    [],
                ),
                (
                    REQUEST_INPUT_COOKIES_MINIMAL_DICT,
                    [
                        "there are cookies in the cookiejar, but ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED is False",
                    ],
                ),
            )
            for settings, setup_warnings in (
                (
                    {},
                    [],
                ),
                (
                    {
                        "COOKIES_ENABLED": True,
                    },
                    [],
                ),
                (
                    {
                        "COOKIES_ENABLED": False,
                    },
                    [],
                ),
                (
                    {
                        "COOKIES_ENABLED": False,
                        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
                    },
                    [
                        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED is True, but it will have no effect because COOKIES_ENABLED is False.",
                    ],
                ),
                (
                    {
                        "COOKIES_ENABLED": False,
                        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": False,
                    },
                    [],
                ),
            )
        ),
        *(
            (
                settings,
                input_cookies,
                {},
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "experimental": {
                        "responseCookies": True,
                        **cast(Dict, output_cookies),
                    },
                },
                [],
                [],
            )
            for input_cookies, output_cookies in (
                (
                    REQUEST_INPUT_COOKIES_EMPTY,
                    {},
                ),
                (
                    REQUEST_INPUT_COOKIES_MINIMAL_DICT,
                    {"requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL},
                ),
            )
            for settings in (
                {
                    "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
                },
                {
                    "COOKIES_ENABLED": True,
                    "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
                },
            )
        ),
        # Do not warn about request cookies not being mapped if cookies are
        # manually set.
        *(
            (
                settings,
                REQUEST_INPUT_COOKIES_MINIMAL_DICT,
                {},
                {
                    "experimental": {
                        "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                    }
                },
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "experimental": {
                        "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                    },
                },
                [],
                [],
            )
            for settings in (
                {},
                {
                    "COOKIES_ENABLED": True,
                },
            )
        ),
        # dont_merge_cookies=True on request metadata disables cookies.
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_EMPTY,
            {
                "dont_merge_cookies": True,
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {
                "dont_merge_cookies": True,
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
            [],
        ),
        # Do not warn about request cookies not being mapped if
        # dont_merge_cookies=True is set on request metadata.
        *(
            (
                settings,
                REQUEST_INPUT_COOKIES_MINIMAL_DICT,
                {
                    "dont_merge_cookies": True,
                },
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                },
                [],
                [
                    {
                        "name": "foo",
                        "value": "bar",
                        "domain": "example.com",
                    }
                ],
            )
            for settings in (
                {},
                {
                    "COOKIES_ENABLED": True,
                },
            )
        ),
        # Cookies can be disabled setting the corresponding Zyte API parameter
        # to False.
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_EMPTY,
            {},
            {
                "experimental": {
                    "responseCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_EMPTY,
            {},
            {
                "experimental": {
                    "requestCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {"responseCookies": True},
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_EMPTY,
            {},
            {
                "experimental": {
                    "responseCookies": False,
                    "requestCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "experimental": {
                    "responseCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                },
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "experimental": {
                    "requestCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {"responseCookies": True},
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "experimental": {
                    "responseCookies": False,
                    "requestCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
            [],
        ),
        # Setting requestCookies to [] disables automatic mapping, but logs a
        # a warning recommending to either use False to achieve the same or
        # remove the parameter to let automatic mapping work.
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "experimental": {
                    "requestCookies": [],
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "requestCookies": [],
                    "responseCookies": True,
                },
            },
            [
                "is overriding automatic request cookie mapping",
            ],
            [],
        ),
        # Cookies work for browser and automatic extraction requests as well.
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "browserHtml": True,
            },
            {
                "browserHtml": True,
                "experimental": {
                    "responseCookies": True,
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                },
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "screenshot": True,
            },
            {
                "screenshot": True,
                "experimental": {
                    "responseCookies": True,
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                },
            },
            [],
            [],
        ),
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                EXTRACT_KEY: True,
            },
            {
                EXTRACT_KEY: True,
                "experimental": {
                    "responseCookies": True,
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                },
            },
            [],
            [],
        ),
        # Cookies are mapped correctly, both with minimum and maximum cookie
        # parameters.
        *(
            (
                {
                    "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
                },
                input,
                {},
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "experimental": {
                        "responseCookies": True,
                        "requestCookies": output,
                    },
                },
                [],
                [],
            )
            for input, output in (
                (
                    REQUEST_INPUT_COOKIES_MINIMAL_DICT,
                    REQUEST_OUTPUT_COOKIES_MINIMAL,
                ),
                (
                    REQUEST_INPUT_COOKIES_MINIMAL_LIST,
                    REQUEST_OUTPUT_COOKIES_MINIMAL,
                ),
                (
                    REQUEST_INPUT_COOKIES_MAXIMAL,
                    REQUEST_OUTPUT_COOKIES_MAXIMAL,
                ),
            )
        ),
        # requestCookies, if set manually, prevents automatic mapping.
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "experimental": {
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MAXIMAL,
                },
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "responseCookies": True,
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MAXIMAL,
                },
            },
            [],
            [],
        ),
        # Mapping multiple cookies works.
        (
            {
                "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
            },
            {"a": "b", "c": "d"},
            {},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "responseCookies": True,
                    "requestCookies": [
                        {"name": "a", "value": "b", "domain": "example.com"},
                        {"name": "c", "value": "d", "domain": "example.com"},
                    ],
                },
            },
            [],
            [],
        ),
    ],
)
@ensureDeferred
async def test_automap_cookies(
    settings, cookies, meta, params, expected, warnings, cookie_jar, caplog
):
    await _test_automap(
        settings,
        {"cookies": cookies, "meta": meta},
        params,
        expected,
        warnings,
        caplog,
        cookie_jar=cookie_jar,
    )


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"zyte_api_automap": {"browserHtml": True}},
    ],
)
@ensureDeferred
async def test_automap_all_cookies(meta):
    """Because of scenarios like cross-domain redirects and browser rendering,
    Zyte API requests should include all cookie jar cookies, regardless of
    the target URL domain."""
    settings: Dict[str, Any] = {
        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    cookie_middleware = get_downloader_middleware(crawler, CookiesMiddleware)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser

    # Start from a cookiejar with an existing cookie for a.example.
    pre_request = Request(
        url="https://a.example",
        meta=meta,
        cookies={"a": "b"},
    )
    cookie_middleware.process_request(pre_request, spider=None)

    # Send a request to c.example, with a cookie for b.example, and ensure that
    # it includes the cookies for a.example and b.example.
    request1 = Request(
        url="https://c.example",
        meta=meta,
        cookies=[
            {
                "name": "c",
                "value": "d",
                "domain": "b.example",
            },
        ],
    )
    cookie_middleware.process_request(request1, spider=None)
    api_params = param_parser.parse(request1)
    assert api_params["experimental"]["requestCookies"] == [
        {"name": "a", "value": "b", "domain": "a.example"},
        # https://github.com/scrapy/scrapy/issues/5841
        # {"name": "c", "value": "d", "domain": "b.example"},
    ]

    # Have the response set 2 cookies for c.example, with and without a domain,
    # and a cookie for  and d.example.
    api_response: Dict[str, Any] = {
        "url": "https://c.example",
        "httpResponseBody": "",
        "statusCode": 200,
        "experimental": {
            "responseCookies": [
                {
                    "name": "e",
                    "value": "f",
                    "domain": ".c.example",
                },
                {
                    "name": "g",
                    "value": "h",
                },
                {
                    "name": "i",
                    "value": "j",
                    "domain": ".d.example",
                },
            ],
        },
    }
    assert handler._cookie_jars is not None  # typing
    response = _process_response(api_response, request1, handler._cookie_jars)
    cookie_middleware.process_response(request1, response, spider=None)

    # Send a second request to e.example, and ensure that cookies
    # for all other domains are included.
    request2 = Request(
        url="https://e.example",
        meta=meta,
    )
    cookie_middleware.process_request(request2, spider=None)
    api_params = param_parser.parse(request2)

    assert sort_dict_list(
        api_params["experimental"]["requestCookies"]
    ) == sort_dict_list(
        [
            {"name": "e", "value": "f", "domain": ".c.example"},
            {"name": "i", "value": "j", "domain": ".d.example"},
            {"name": "a", "value": "b", "domain": "a.example"},
            {"name": "g", "value": "h", "domain": "c.example"},
            # https://github.com/scrapy/scrapy/issues/5841
            # {"name": "c", "value": "d", "domain": "b.example"},
        ]
    )


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"zyte_api_automap": {"browserHtml": True}},
    ],
)
@ensureDeferred
async def test_automap_cookie_jar(meta):
    """Test that cookies from the right jar are used."""
    request1 = Request(
        url="https://example.com/1", meta={**meta, "cookiejar": "a"}, cookies={"z": "y"}
    )
    request2 = Request(url="https://example.com/2", meta={**meta, "cookiejar": "b"})
    request3 = Request(
        url="https://example.com/3", meta={**meta, "cookiejar": "a"}, cookies={"x": "w"}
    )
    request4 = Request(url="https://example.com/4", meta={**meta, "cookiejar": "a"})
    settings: Dict[str, Any] = {
        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    cookie_middleware = get_downloader_middleware(crawler, CookiesMiddleware)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser

    cookie_middleware.process_request(request1, spider=None)
    api_params = param_parser.parse(request1)
    assert api_params["experimental"]["requestCookies"] == [
        {"name": "z", "value": "y", "domain": "example.com"}
    ]

    cookie_middleware.process_request(request2, spider=None)
    api_params = param_parser.parse(request2)
    assert "requestCookies" not in api_params["experimental"]

    cookie_middleware.process_request(request3, spider=None)

    api_params = param_parser.parse(request3)
    assert sort_dict_list(
        api_params["experimental"]["requestCookies"]
    ) == sort_dict_list(
        [
            {"name": "x", "value": "w", "domain": "example.com"},
            {"name": "z", "value": "y", "domain": "example.com"},
        ]
    )

    cookie_middleware.process_request(request4, spider=None)
    api_params = param_parser.parse(request4)
    assert sort_dict_list(
        api_params["experimental"]["requestCookies"]
    ) == sort_dict_list(
        [
            {"name": "x", "value": "w", "domain": "example.com"},
            {"name": "z", "value": "y", "domain": "example.com"},
        ]
    )


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"zyte_api_automap": {"browserHtml": True}},
    ],
)
@ensureDeferred
async def test_automap_cookie_limit(meta, caplog):
    settings: Dict[str, Any] = {
        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
        "ZYTE_API_MAX_COOKIES": 1,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    cookie_middleware = get_downloader_middleware(crawler, CookiesMiddleware)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    cookiejar = 0

    # Verify that request with 1 cookie works as expected.
    request = Request(
        url="https://example.com/1",
        meta={**meta, "cookiejar": cookiejar},
        cookies={"z": "y"},
    )
    cookiejar += 1
    cookie_middleware.process_request(request, spider=None)
    caplog.clear()
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    assert api_params["experimental"]["requestCookies"] == [
        {"name": "z", "value": "y", "domain": "example.com"}
    ]
    assert not caplog.records
    caplog.clear()

    # Verify that requests with 2 cookies results in only 1 cookie set and a
    # warning.
    request = Request(
        url="https://example.com/1",
        meta={**meta, "cookiejar": cookiejar},
        cookies={"z": "y", "x": "w"},
    )
    cookiejar += 1
    cookie_middleware.process_request(request, spider=None)
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    assert api_params["experimental"]["requestCookies"] in [
        [{"name": "z", "value": "y", "domain": "example.com"}],
        [{"name": "x", "value": "w", "domain": "example.com"}],
    ]
    assert "would get 2 cookies" in caplog.text
    assert "limited to 1 cookies" in caplog.text
    caplog.clear()

    # Verify that 1 cookie in the cookie jar and 1 cookie in the request count
    # as 2 cookies, resulting in only 1 cookie set and a warning.
    pre_request = Request(
        url="https://example.com/1",
        meta={**meta, "cookiejar": cookiejar},
        cookies={"z": "y"},
    )
    cookie_middleware.process_request(pre_request, spider=None)
    request = Request(
        url="https://example.com/1",
        meta={**meta, "cookiejar": cookiejar},
        cookies={"x": "w"},
    )
    cookiejar += 1
    cookie_middleware.process_request(request, spider=None)
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    assert api_params["experimental"]["requestCookies"] in [
        [{"name": "z", "value": "y", "domain": "example.com"}],
        [{"name": "x", "value": "w", "domain": "example.com"}],
    ]
    assert "would get 2 cookies" in caplog.text
    assert "limited to 1 cookies" in caplog.text
    caplog.clear()

    # Vefify that unrelated-domain cookies count for the limit.
    pre_request = Request(
        url="https://other.example/1",
        meta={**meta, "cookiejar": cookiejar},
        cookies={"z": "y"},
    )
    cookie_middleware.process_request(pre_request, spider=None)
    request = Request(
        url="https://example.com/1",
        meta={**meta, "cookiejar": cookiejar},
        cookies={"x": "w"},
    )
    cookiejar += 1
    cookie_middleware.process_request(request, spider=None)
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    assert api_params["experimental"]["requestCookies"] in [
        [{"name": "z", "value": "y", "domain": "other.example"}],
        [{"name": "x", "value": "w", "domain": "example.com"}],
    ]
    assert "would get 2 cookies" in caplog.text
    assert "limited to 1 cookies" in caplog.text
    caplog.clear()


class CustomCookieJar(CookieJar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jar.set_cookie(
            Cookie(
                1,
                "z",
                "y",
                None,
                False,
                "example.com",
                True,
                False,
                "/",
                False,
                False,
                None,
                False,
                None,
                None,
                {},
            )
        )


class CustomCookieMiddleware(CookiesMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jars = defaultdict(CustomCookieJar)


@ensureDeferred
async def test_automap_custom_cookie_middleware():
    mw_cls = CustomCookieMiddleware
    settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy.downloadermiddlewares.cookies.CookiesMiddleware": None,
            f"{mw_cls.__module__}.{mw_cls.__qualname__}": 700,
        },
        "ZYTE_API_COOKIE_MIDDLEWARE": f"{mw_cls.__module__}.{mw_cls.__qualname__}",
        "ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    cookie_middleware = get_downloader_middleware(crawler, mw_cls)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser

    request = Request(url="https://example.com/1")
    cookie_middleware.process_request(request, spider=None)
    api_params = param_parser.parse(request)
    assert api_params["experimental"]["requestCookies"] == [
        {"name": "z", "value": "y", "domain": "example.com"}
    ]


@pytest.mark.parametrize(
    "body,meta,expected,warnings",
    [
        # The body is copied into httpRequestBody, base64-encoded.
        (
            "a",
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestBody": "YQ==",
            },
            [],
        ),
        # httpRequestBody defined in meta takes precedence, but it causes a
        # warning.
        (
            "a",
            {"httpRequestBody": "Yg=="},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestBody": "Yg==",
            },
            [
                "Use Request.body instead",
                "does not match the Zyte API httpRequestBody parameter",
            ],
        ),
        # httpRequestBody defined in meta causes a warning even if it matches
        # request.body.
        (
            "a",
            {"httpRequestBody": "YQ=="},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestBody": "YQ==",
            },
            ["Use Request.body instead"],
        ),
        # The body is mapped even if httpResponseBody is not used.
        (
            "a",
            {"browserHtml": True},
            {
                "browserHtml": True,
                "httpRequestBody": "YQ==",
            },
            [],
        ),
        (
            "a",
            {"screenshot": True},
            {
                "httpRequestBody": "YQ==",
                "screenshot": True,
            },
            [],
        ),
        (
            "a",
            {EXTRACT_KEY: True},
            {
                "httpRequestBody": "YQ==",
                EXTRACT_KEY: True,
            },
            [],
        ),
    ],
)
@ensureDeferred
async def test_automap_body(body, meta, expected, warnings, caplog):
    await _test_automap({}, {"body": body}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        # When httpResponseBody, browserHtml, screenshot, automatic extraction
        # properties, or httpResponseHeaders, are unnecessarily set to False,
        # they are not defined in the parameters sent to Zyte API, and a
        # warning is logged.
        (
            {
                "browserHtml": True,
                "httpResponseBody": False,
            },
            {
                "browserHtml": True,
            },
            ["unnecessarily defines"],
        ),
        (
            {
                "browserHtml": False,
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["unnecessarily defines"],
        ),
        (
            {
                "screenshot": False,
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["unnecessarily defines"],
        ),
        (
            {
                "httpResponseHeaders": False,
                "screenshot": True,
            },
            {
                "screenshot": True,
            },
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {
                EXTRACT_KEY: False,
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["unnecessarily defines"],
        ),
        (
            {
                "httpResponseHeaders": False,
                EXTRACT_KEY: True,
            },
            {
                EXTRACT_KEY: True,
            },
            ["do not need to set httpResponseHeaders to False"],
        ),
    ],
)
@ensureDeferred
async def test_automap_default_parameter_cleanup(meta, expected, warnings, caplog):
    await _test_automap({}, {}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "default_params,meta,expected,warnings",
    [
        (
            {"browserHtml": True},
            {"screenshot": True, "browserHtml": False},
            {
                "screenshot": True,
            },
            [],
        ),
        (
            {},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
    ],
)
@ensureDeferred
async def test_default_params_automap(default_params, meta, expected, warnings, caplog):
    """Warnings about unneeded parameters should not apply if those parameters
    are needed to extend or override parameters set in the
    ``ZYTE_API_AUTOMAP_PARAMS`` setting."""
    request = Request(url="https://example.com")
    request.meta["zyte_api_automap"] = meta
    settings = {
        "ZYTE_API_AUTOMAP_PARAMS": default_params,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    caplog.clear()
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    api_params.pop("url")
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records


@pytest.mark.parametrize(
    "default_params",
    [
        {"browserHtml": True},
        {},
    ],
)
@ensureDeferred
async def test_default_params_false(default_params):
    """If zyte_api_default_params=False is passed, ZYTE_API_DEFAULT_PARAMS is ignored."""
    request = Request(url="https://example.com")
    request.meta["zyte_api_default_params"] = False
    settings = {
        "ZYTE_API_DEFAULT_PARAMS": default_params,
    }
    crawler = await get_crawler(settings)
    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params is None


@ensureDeferred
async def _process_request(crawler, request, is_start_request=False):
    spider = crawler.spider

    await crawler.engine.scraper.open_spider(spider)
    await crawler.engine.signals.send_catch_log_deferred(
        signals.spider_opened, spider=spider
    )

    spider_middlewares = crawler.engine.scraper.spidermw
    if is_start_request:
        result = await spider_middlewares.process_start_requests([request], spider)
        request = next(result)
    else:
        response = Response(request.url, request=request)
        _, request, _ = await spider_middlewares.scrape_response(
            lambda *args: args, response, request, spider
        )

    downloader_middlewares = crawler.engine.downloader.middleware
    for process_request in downloader_middlewares.methods["process_request"]:
        result = process_request(request=request, spider=spider)
        if asyncio.isfuture(result) or inspect.isawaitable(result):
            await result


@ensureDeferred
async def test_middleware_headers_start_requests():
    """By default, automap should not generate a customHttpRequestHeaders
    parameter."""
    crawler = await get_crawler({"ZYTE_API_TRANSPARENT_MODE": True})
    request = Request(url="https://example.com")
    await _process_request(crawler, request, is_start_request=True)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert "customHttpRequestHeaders" not in api_params


@ensureDeferred
async def test_middleware_headers_cb_requests():
    """Callback requests will include the Referer parameter if the Referer
    middleware is not disabled."""
    crawler = await get_crawler({"ZYTE_API_TRANSPARENT_MODE": True})
    request = Request(url="https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {"name": "Referer", "value": request.url},
    ]


@ensureDeferred
async def test_middleware_headers_cb_requests_disable():
    """Callback requests will not include the Referer parameter if the Referer
    middleware is disabled."""
    settings = {
        "REFERER_ENABLED": False,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(url="https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert "customHttpRequestHeaders" not in api_params


@ensureDeferred
async def test_middleware_headers_cb_requests_skip():
    """Callback requests will not include the Referer parameter if the Referer
    header is configured to be skipped."""
    settings = {
        "ZYTE_API_SKIP_HEADERS": list(
            set(header.decode() for header in SKIP_HEADERS)
            | {
                "Referer",
            }
        ),
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(url="https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert "customHttpRequestHeaders" not in api_params


@ensureDeferred
async def test_middleware_headers_default():
    """If DEFAULT_REQUEST_HEADERS is user-defined, even with the same value as
    the global default, and values matching defaults from middlewares that are
    ignored otherwise, its headers should be translated into the
    customHttpRequestHeaders parameter."""
    settings = {
        "DEFAULT_REQUEST_HEADERS": {
            **DEFAULT_REQUEST_HEADERS,
            "Accept-Encoding": DEFAULT_ACCEPT_ENCODING,
            "User-Agent": DEFAULT_USER_AGENT,
        },
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(url="https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {"name": "Referer", "value": request.url},
        {
            "name": "Accept",
            "value": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        {"name": "Accept-Language", "value": "en"},
        {
            "name": "Accept-Encoding",
            "value": DEFAULT_ACCEPT_ENCODING,
        },
        {
            "name": "User-Agent",
            "value": DEFAULT_USER_AGENT,
        },
    ]


@ensureDeferred
async def test_middleware_headers_default_custom():
    """Non-default values set for headers with a default value also work as
    expected."""
    settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html",
            "Accept-Language": "fa",
            "Accept-Encoding": "br",
            "Referer": "https://referrer.example",
            "User-Agent": "foo/1.2.3",
        },
        "REFERER_ENABLED": False,  # https://github.com/scrapy/scrapy/issues/6184
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(url="https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {
            "name": "Accept",
            "value": "text/html",
        },
        {"name": "Accept-Language", "value": "fa"},
        {
            "name": "Accept-Encoding",
            "value": "br",
        },
        {"name": "Referer", "value": "https://referrer.example"},
        {"name": "User-Agent", "value": "foo/1.2.3"},
    ]


@ensureDeferred
async def test_middleware_headers_default_skip():
    """Headers set through DEFAULT_REQUEST_HEADERS will not be translated into
    the customHttpRequestHeaders parameter if configured to be skipped."""
    settings = {
        "DEFAULT_REQUEST_HEADERS": {
            **DEFAULT_REQUEST_HEADERS,
            "Accept-Encoding": DEFAULT_ACCEPT_ENCODING,
            "User-Agent": DEFAULT_USER_AGENT,
        },
        "ZYTE_API_SKIP_HEADERS": list(
            set(header.decode() for header in SKIP_HEADERS)
            | {*DEFAULT_REQUEST_HEADERS, "Accept-Encoding", "Referer", "User-Agent"}
        ),
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(url="https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert "customHttpRequestHeaders" not in api_params


@ensureDeferred
async def test_middleware_headers_request_headers():
    """If request headers match the global default value of
    DEFAULT_REQUEST_HEADERS, they should be translated nonetheless."""
    settings = {
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(
        url="https://example.com",
        headers={
            **DEFAULT_REQUEST_HEADERS,
            "Accept-Encoding": DEFAULT_ACCEPT_ENCODING,
            "User-Agent": DEFAULT_USER_AGENT,
        },
    )
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {
            "name": "Accept",
            "value": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        {"name": "Accept-Language", "value": "en"},
        {
            "name": "Accept-Encoding",
            "value": DEFAULT_ACCEPT_ENCODING,
        },
        {"name": "User-Agent", "value": DEFAULT_USER_AGENT},
        {"name": "Referer", "value": request.url},
    ]


@ensureDeferred
async def test_middleware_headers_request_headers_custom():
    """Non-default values set for headers with a default value also work as
    expected."""
    crawler = await get_crawler({"ZYTE_API_TRANSPARENT_MODE": True})
    request = Request(
        url="https://example.com",
        headers={
            "Accept": "text/html",
            "Accept-Language": "fa",
            "Accept-Encoding": "br",
            "Referer": "https://referrer.example",
            "User-Agent": "foo/1.2.3",
        },
    )
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {
            "name": "Accept",
            "value": "text/html",
        },
        {"name": "Accept-Language", "value": "fa"},
        {
            "name": "Accept-Encoding",
            "value": "br",
        },
        {"name": "Referer", "value": "https://referrer.example"},
        {"name": "User-Agent", "value": "foo/1.2.3"},
    ]


@ensureDeferred
async def test_middleware_headers_request_headers_skip():
    """Headers set on the request will not be translated into the
    customHttpRequestHeaders parameter if configured to be skipped."""
    settings = {
        "ZYTE_API_SKIP_HEADERS": list(
            set(header.decode() for header in SKIP_HEADERS)
            | {*DEFAULT_REQUEST_HEADERS, "Accept-Encoding", "Referer", "User-Agent"}
        ),
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    request = Request(
        url="https://example.com",
        headers={
            **DEFAULT_REQUEST_HEADERS,
            "Accept-Encoding": DEFAULT_ACCEPT_ENCODING,
            "User-Agent": DEFAULT_USER_AGENT,
        },
    )
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert "customHttpRequestHeaders" not in api_params


class DefaultValuesDownloaderMiddleware:
    def process_request(self, request, spider):
        for k, v in {
            **DEFAULT_REQUEST_HEADERS,
            "Accept-Encoding": DEFAULT_ACCEPT_ENCODING,
            "User-Agent": DEFAULT_USER_AGENT,
        }.items():
            request.headers[k] = v


@ensureDeferred
async def test_middleware_headers_custom_middleware_before():
    """If request headers defined from a custom middleware configured before
    the scrapy-zyte-api downloader middleware match the global default value of
    DEFAULT_REQUEST_HEADERS, they will *not* be translated."""

    settings: SETTINGS_T = {
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    mw1 = "tests.test_api_requests.DefaultValuesDownloaderMiddleware"
    mw2 = "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware"
    settings["DOWNLOADER_MIDDLEWARES"] = {
        **SETTINGS["DOWNLOADER_MIDDLEWARES"],
        mw1: SETTINGS["DOWNLOADER_MIDDLEWARES"][mw2] - 1,
    }
    crawler = await get_crawler(settings)
    request = Request("https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {"name": "Referer", "value": request.url},
    ]


class CustomValuesDownloaderMiddleware:
    def process_request(self, request, spider):
        for k, v in {
            "Accept": "text/html",
            "Accept-Language": "fa",
            "Accept-Encoding": "br",
            "Referer": "https://referrer.example",
            "User-Agent": "foo/1.2.3",
        }.items():
            request.headers[k] = v


@ensureDeferred
async def test_middleware_headers_custom_middleware_before_custom():
    """If request headers defined from a custom middleware configured before
    the scrapy-zyte-api downloader middleware have non-default values, they
    will be translated."""
    settings: SETTINGS_T = {
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    mw1 = "tests.test_api_requests.CustomValuesDownloaderMiddleware"
    mw2 = "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware"
    settings["DOWNLOADER_MIDDLEWARES"] = {
        **SETTINGS["DOWNLOADER_MIDDLEWARES"],
        mw1: SETTINGS["DOWNLOADER_MIDDLEWARES"][mw2] - 1,
    }
    crawler = await get_crawler(settings)
    request = Request("https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert api_params["customHttpRequestHeaders"] == [
        {"name": "Referer", "value": "https://referrer.example"},
        {
            "name": "Accept",
            "value": "text/html",
        },
        {"name": "Accept-Language", "value": "fa"},
        {"name": "User-Agent", "value": "foo/1.2.3"},
        {
            "name": "Accept-Encoding",
            "value": "br",
        },
    ]


@ensureDeferred
async def test_middleware_headers_custom_middleware_before_skip():
    """Headers set on the request from a custom middleware configured before
    the scrapy-zyte-api downloader middleware will not be translated into the
    customHttpRequestHeaders parameter if configured to be skipped."""

    settings = {
        "ZYTE_API_SKIP_HEADERS": list(
            set(header.decode() for header in SKIP_HEADERS)
            | {*DEFAULT_REQUEST_HEADERS, "Accept-Encoding", "Referer", "User-Agent"}
        ),
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    mw1 = "tests.test_api_requests.CustomValuesDownloaderMiddleware"
    mw2 = "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware"
    settings["DOWNLOADER_MIDDLEWARES"] = {
        **SETTINGS["DOWNLOADER_MIDDLEWARES"],
        mw1: SETTINGS["DOWNLOADER_MIDDLEWARES"][mw2] - 1,
    }
    crawler = await get_crawler(settings)
    request = Request("https://example.com")
    await _process_request(crawler, request)

    handler = get_download_handler(crawler, "https")
    param_parser = handler._param_parser
    api_params = param_parser.parse(request)
    assert "customHttpRequestHeaders" not in api_params
