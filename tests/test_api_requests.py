import sys
from asyncio import iscoroutine
from copy import copy
from functools import partial
from inspect import isclass
from typing import Any, Dict
from unittest import mock
from unittest.mock import patch

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware
from scrapy.exceptions import CloseSpider, NotConfigured
from scrapy.http import Response, TextResponse
from scrapy.settings.default_settings import DEFAULT_REQUEST_HEADERS
from scrapy.settings.default_settings import USER_AGENT as DEFAULT_USER_AGENT
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler
from twisted.internet.defer import Deferred
from zyte_api.aio.errors import RequestError

from scrapy_zyte_api.handler import _ParamParser

from . import DEFAULT_CLIENT_CONCURRENCY, SETTINGS
from .mockserver import DelayedResource, MockServer, produce_request_response


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
                "Got Zyte API error (status=422, "
                "type='/request/unprocessable') while processing URL "
                "(http://example.com): Incompatible parameters were found in "
                "the request."
            ),
        ),
    ],
)
async def test_exceptions(
    caplog: LogCaptureFixture,
    meta: Dict[str, Dict[str, Any]],
    exception_type: Exception,
    exception_text: str,
    mockserver,
):
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

        crawler = get_crawler(
            TestSpider,
            {
                **SETTINGS,
                "CONCURRENT_REQUESTS": concurrency,
                "CONCURRENT_REQUESTS_PER_DOMAIN": concurrency,
                "ZYTE_API_URL": server.urljoin("/"),
            },
        )
        await crawler.crawl()

    assert response_indexes[0] == expected_first_index


AUTOMAP_PARAMS: Dict[str, Any] = {}
BROWSER_HEADERS = {b"referer": "referer"}
DEFAULT_PARAMS: Dict[str, Any] = {}
TRANSPARENT_MODE = False
SKIP_HEADERS = {b"cookie", b"user-agent"}
JOB_ID = None
GET_API_PARAMS_KWARGS = {
    "default_params": DEFAULT_PARAMS,
    "transparent_mode": TRANSPARENT_MODE,
    "automap_params": AUTOMAP_PARAMS,
    "skip_headers": SKIP_HEADERS,
    "browser_headers": BROWSER_HEADERS,
    "job_id": JOB_ID,
}


@ensureDeferred
async def test_params_parser_input_default(mockserver):
    async with mockserver.make_handler() as handler:
        for key in GET_API_PARAMS_KWARGS:
            actual = getattr(handler._param_parser, f"_{key}")
            expected = GET_API_PARAMS_KWARGS[key]
            assert actual == expected


@ensureDeferred
async def test_param_parser_input_custom(mockserver):
    settings = {
        "JOB": "1/2/3",
        "ZYTE_API_AUTOMAP_PARAMS": {"c": "d"},
        "ZYTE_API_BROWSER_HEADERS": {"B": "b"},
        "ZYTE_API_DEFAULT_PARAMS": {"a": "b"},
        "ZYTE_API_SKIP_HEADERS": {"A"},
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    async with mockserver.make_handler(settings) as handler:
        parser = handler._param_parser
        assert parser._automap_params == {"c": "d"}
        assert parser._browser_headers == {b"b": "b"}
        assert parser._default_params == {"a": "b"}
        assert parser._job_id == "1/2/3"
        assert parser._skip_headers == {b"a"}
        assert parser._transparent_mode is True


@ensureDeferred
@pytest.mark.skipif(sys.version_info < (3, 8), reason="unittest.mock.AsyncMock")
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
        patch_path = "scrapy_zyte_api.handler.super"
        with patch(patch_path) as super:
            handler._download_request = mock.AsyncMock(side_effect=RuntimeError)
            super_mock = mock.Mock()
            super_mock.download_request = mock.AsyncMock(side_effect=RuntimeError)
            super.return_value = super_mock
            with pytest.raises(RuntimeError):
                await handler.download_request(request, None)
    if uses_zyte_api:
        handler._download_request.assert_called()
    else:
        super_mock.download_request.assert_called()


DEFAULT_AUTOMAP_PARAMS: Dict[str, Any] = {
    "httpResponseBody": True,
    "httpResponseHeaders": True,
    "experimental": {"responseCookies": True},
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
def test_transparent_mode_toggling(setting, meta, expected):
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
    crawler = get_crawler(settings_dict=settings)
    param_parser = _ParamParser(crawler.settings)
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
def test_api_disabling_deprecated(meta):
    """Test how undocumented falsy values of the ``zyte_api`` request metadata
    key (*meta*) can be used to disable the use of Zyte API, but trigger a
    deprecation warning asking to replace them with False."""
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = meta
    crawler = get_crawler()
    param_parser = _ParamParser(crawler.settings)
    with pytest.warns(DeprecationWarning, match=r".* Use False instead\.$"):
        api_params = param_parser.parse(request)
    assert api_params is None


@pytest.mark.parametrize("key", ["zyte_api", "zyte_api_automap"])
@pytest.mark.parametrize("value", [1, ["a", "b"]])
def test_bad_meta_type(key, value):
    """Test how undocumented truthy values (*value*) for the ``zyte_api`` and
    ``zyte_api_automap`` request metadata keys (*key*) trigger a
    :exc:`ValueError` exception."""
    request = Request(url="https://example.com", meta={key: value})
    crawler = get_crawler()
    param_parser = _ParamParser(crawler.settings)
    with pytest.raises(ValueError):
        param_parser.parse(request)


@pytest.mark.parametrize("meta", ["zyte_api", "zyte_api_automap"])
@ensureDeferred
async def test_job_id(meta, mockserver):
    """Test how the value of the ``JOB`` setting is included as ``jobId`` among
    the parameters sent to Zyte API, both with manually-defined parameters and
    with automatically-mapped parameters.

    Note that :func:`test_param_parser_input_custom` already tests how the
    ``JOB`` setting is mapped to the corresponding
    :func:`~scrapy_zyte_api.handler._get_api_params` parameter.
    """
    request = Request(url="https://example.com", meta={meta: True})
    settings = {"JOB": "1/2/3"}
    crawler = get_crawler(settings_dict=settings)
    param_parser = _ParamParser(crawler.settings)
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
        ({}, {"b": None}, {}, ["does not define such a parameter"]),
        ({"a": 1}, {}, {"a": 1}, []),
        ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}, []),
        ({"a": 1}, {"b": None}, {"a": 1}, ["does not define such a parameter"]),
        ({"a": 1}, {"a": 2}, {"a": 2}, []),
        ({"a": 1}, {"a": None}, {}, []),
    ],
)
@pytest.mark.parametrize(
    "setting_key,meta_key,ignore_keys",
    [
        ("ZYTE_API_DEFAULT_PARAMS", "zyte_api", set()),
        (
            "ZYTE_API_AUTOMAP_PARAMS",
            "zyte_api_automap",
            {"httpResponseBody", "httpResponseHeaders", "experimental"},
        ),
    ],
)
def test_default_params_merging(
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
    settings = {setting_key: setting}
    crawler = get_crawler(settings_dict=settings)
    param_parser = _ParamParser(crawler.settings)
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
def test_default_params_immutability(setting_key, meta_key, setting, meta):
    """Make sure that the merging of Zyte API parameters from the *arg_key*
    _get_api_params parameter with those from the *meta_key* request metadata
    key does not affect the contents of the setting for later requests."""
    request = Request(url="https://example.com")
    request.meta[meta_key] = meta
    default_params = copy(setting)
    settings = {setting_key: setting}
    crawler = get_crawler(settings_dict=settings)
    param_parser = _ParamParser(crawler.settings)
    param_parser.parse(request)
    assert default_params == setting


def _test_automap(settings, request_kwargs, meta, expected, warnings, caplog):
    request = Request(url="https://example.com", **request_kwargs)
    request.meta["zyte_api_automap"] = meta
    settings = {**settings, "ZYTE_API_TRANSPARENT_MODE": True}
    crawler = get_crawler(settings_dict=settings)
    if "cookies" in request_kwargs:
        try:
            cookie_middleware = create_instance(
                CookiesMiddleware,
                settings=crawler.settings,
                crawler=crawler,
            )
        except NotConfigured:
            pass
        else:
            cookie_middleware.process_request(request, spider=None)
    param_parser = _ParamParser(crawler.settings)
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
        # in cases where a binary response is expected, since automated mapping
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
    ],
)
def test_automap_main_outputs(meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap({}, {}, meta, expected, warnings, caplog)


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
def test_automap_header_output(meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap({}, {}, meta, expected, warnings, caplog)


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
        *(
            (
                request_method,
                {"httpRequestMethod": meta_method},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "httpRequestMethod": meta_method,
                },
                ["Use Request.method"],
            )
            for request_method, meta_method in (
                ("GET", "GET"),
                ("POST", "POST"),
            )
        ),
        # If httpRequestMethod is also specified in meta with a different value
        # from Request.method, a warning is logged asking to use Request.meta,
        # and the meta value takes precedence.
        *(
            (
                request_method,
                {"httpRequestMethod": meta_method},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "httpRequestMethod": meta_method,
                },
                [
                    "Use Request.method",
                    "does not match the Zyte API httpRequestMethod",
                ],
            )
            for request_method, meta_method in (
                ("GET", "POST"),
                ("PUT", "GET"),
            )
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
    ],
)
def test_automap_method(method, meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap({}, {"method": method}, meta, expected, warnings, caplog)


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
        # If browserHtml or screenshot are True, Request.headers are mapped as
        # requestHeaders.
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
        # If both httpResponseBody and browserHtml (or screenshot, or both) are
        # True, implicitly or explicitly, Request.headers are mapped both as
        # customHttpRequestHeaders and as requestHeaders.
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
        # Unsupported headers are looked up case-insensitively.
        (
            {"user-Agent": ""},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # The Accept and Accept-Language headers, when unsupported, are dropped
        # silently if their value matches the default value of Scrapy for
        # DEFAULT_REQUEST_HEADERS, or with a warning otherwise.
        (
            {
                k: v
                for k, v in DEFAULT_REQUEST_HEADERS.items()
                if k in {"Accept", "Accept-Language"}
            },
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            [],
        ),
        (
            {
                "Accept": "application/json",
                "Accept-Language": "uk",
            },
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            ["cannot be mapped"],
        ),
        # The User-Agent header, which Scrapy sets by default, is dropped
        # silently if it matches the default value of the USER_AGENT setting,
        # or with a warning otherwise.
        (
            {"User-Agent": DEFAULT_USER_AGENT},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"User-Agent": ""},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        (
            {"User-Agent": DEFAULT_USER_AGENT},
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            [],
        ),
        (
            {"User-Agent": ""},
            {"browserHtml": True},
            {
                "browserHtml": True,
            },
            ["cannot be mapped"],
        ),
    ],
)
def test_automap_headers(headers, meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap({}, {"headers": headers}, meta, expected, warnings, caplog)


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
def test_automap_header_settings(settings, headers, meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap(settings, {"headers": headers}, meta, expected, warnings, caplog)


REQUEST_INPUT_COOKIES_EMPTY: Dict[str, str] = {}
REQUEST_INPUT_COOKIES_MINIMAL_DICT = {"a": "b"}
REQUEST_INPUT_COOKIES_MINIMAL_LIST = [{"name": "a", "value": "b"}]
REQUEST_INPUT_COOKIES_MAXIMAL = [
    {"name": "c", "value": "d", "domain": "example.com", "path": "/"}
]
# TODO: Find out how to define an output cookie that works for the URL domain
# but not for a subdomain.
REQUEST_OUTPUT_COOKIES_MINIMAL = [{"name": "a", "value": "b", "domain": ""}]
REQUEST_OUTPUT_COOKIES_MAXIMAL = [
    {"name": "c", "value": "d", "domain": "example.com", "path": "/"}
]


@pytest.mark.parametrize(
    "settings,cookies,meta,expected",
    [
        # Cookies, both for requests and for responses, are enabled based on
        # COOKIES_ENABLED (default: True).
        (
            {
                "COOKIES_ENABLED": False,
            },
            REQUEST_INPUT_COOKIES_EMPTY,
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
        ),
        (
            {
                "COOKIES_ENABLED": False,
            },
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_EMPTY,
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {"responseCookies": True},
            },
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "responseCookies": True,
                    "requestCookies": REQUEST_OUTPUT_COOKIES_MINIMAL,
                },
            },
        ),
        # Cookies can be disabled setting the corresponding Zyte API parameter
        # to False.
        (
            {},
            REQUEST_INPUT_COOKIES_EMPTY,
            {
                "experimental": {
                    "responseCookies": False,
                }
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_EMPTY,
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
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_EMPTY,
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
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
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
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
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
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
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
        ),
        # Cookies work for browser requests as well.
        (
            {},
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
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
        ),
        (
            {},
            REQUEST_INPUT_COOKIES_MINIMAL_DICT,
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
        ),
        # Cookies are mapped correctly, both with minimum and maximum cookie
        # parameters.
        *(
            (
                {},
                input,
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "experimental": {
                        "responseCookies": True,
                        "requestCookies": output,
                    },
                },
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
    ],
    # TODO: Cover scenarios involving default params.
    # TODO: Cover scenarios involving multiple cookies.
    # TODO: Handle the scenario of a browser request, which on the server side
    # could involve multiple requests for different domains. The current
    # implementation lets the Scrapy cookie middleware set the right cookies
    # into the Cookie header, but those are limited to cookies relevant for the
    # target URL. In browser requests, we should include all jar cookies,
    # regardless of domain, and let Zyte API include the right ones on each
    # URL. Also, depending on how redirects are handled for non-browser
    # requests, this may also apply to those.
)
def test_automap_cookies(settings, cookies, meta, expected, caplog):
    _test_automap(settings, {"cookies": cookies}, meta, expected, [], caplog)


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
    ],
)
def test_automap_body(body, meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap({}, {"body": body}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        # When httpResponseBody, browserHtml, screenshot, or
        # httpResponseHeaders, are unnecessarily set to False, they are not
        # defined in the parameters sent to Zyte API, and a warning is logged.
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
    ],
)
def test_automap_default_parameter_cleanup(meta, expected, warnings, caplog):
    expected = {
        "experimental": {
            "responseCookies": True,
        },
        **expected,
    }
    _test_automap({}, {}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "default_params,meta,expected,warnings",
    [
        (
            {"browserHtml": True},
            {"screenshot": True, "browserHtml": False},
            {
                "screenshot": True,
                "experimental": {
                    "responseCookies": True,
                },
            },
            [],
        ),
    ],
)
def test_default_params_automap(default_params, meta, expected, warnings, caplog):
    """Warnings about unneeded parameters should not apply if those parameters
    are needed to extend or override parameters set in the
    ``ZYTE_API_AUTOMAP_PARAMS`` setting."""
    request = Request(url="https://example.com")
    request.meta["zyte_api_automap"] = meta
    settings = {
        "ZYTE_API_AUTOMAP_PARAMS": default_params,
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = get_crawler(settings_dict=settings)
    param_parser = _ParamParser(crawler.settings)
    with caplog.at_level("WARNING"):
        api_params = param_parser.parse(request)
    api_params.pop("url")
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records
