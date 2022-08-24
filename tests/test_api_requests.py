import sys
from asyncio import iscoroutine
from typing import Any, Dict, List, Literal, Union
from unittest import mock

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.exceptions import NotSupported
from scrapy.http import Response, TextResponse
from scrapy.settings.default_settings import DEFAULT_REQUEST_HEADERS
from scrapy.settings.default_settings import USER_AGENT as DEFAULT_USER_AGENT
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.test import get_crawler
from twisted.internet.defer import Deferred
from zyte_api.aio.errors import RequestError

from . import DEFAULT_CLIENT_CONCURRENCY, SETTINGS
from .mockserver import DelayedResource, MockServer, produce_request_response


@ensureDeferred
@pytest.mark.parametrize(
    "meta",
    [
        {"zyte_api": {"browserHtml": True}},
        {"zyte_api": {"browserHtml": True, "geolocation": "US"}},
        {"zyte_api": {"browserHtml": True, "geolocation": "US", "echoData": 123}},
        {"zyte_api": {"browserHtml": True, "randomParameter": None}},
        {"zyte_api": {"httpResponseBody": True}},
        {"zyte_api": {"httpResponseBody": True, "geolocation": "US"}},
        {
            "zyte_api": {
                "httpResponseBody": True,
                "geolocation": "US",
                "echoData": 123,
            }
        },
        {"zyte_api": {"httpResponseBody": True, "randomParameter": None}},
    ],
)
async def test_html_response_and_headers(meta: Dict[str, Dict[str, Any]], mockserver):
    req, resp = await produce_request_response(mockserver, meta)
    assert isinstance(resp, TextResponse)
    assert resp.request is req
    assert resp.url == req.url
    assert resp.status == 200
    assert "zyte-api" in resp.flags
    assert resp.body == b"<html><body>Hello<h1>World!</h1></body></html>"
    assert resp.text == "<html><body>Hello<h1>World!</h1></body></html>"
    assert resp.css("h1 ::text").get() == "World!"
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    assert resp.headers == {b"Test_Header": [b"test_value"]}


@pytest.mark.parametrize(
    "meta",
    [
        {"zyte_api": {"httpResponseBody": True, "httpResponseHeaders": False}},
        {
            "zyte_api": {
                "httpResponseBody": True,
                "httpResponseHeaders": False,
                "geolocation": "US",
            },
        },
        {
            "zyte_api": {
                "httpResponseBody": True,
                "httpResponseHeaders": False,
                "geolocation": "US",
                "echoData": 123,
            }
        },
        {
            "zyte_api": {
                "httpResponseBody": True,
                "httpResponseHeaders": False,
                "randomParameter": None,
            },
        },
    ],
)
@ensureDeferred
async def test_http_response_body_request(meta: Dict[str, Dict[str, Any]], mockserver):
    req, resp = await produce_request_response(mockserver, meta)
    assert isinstance(resp, Response)
    assert resp.request is req
    assert resp.url == req.url
    assert resp.status == 200
    assert "zyte-api" in resp.flags
    assert resp.body == b"<html><body>Hello<h1>World!</h1></body></html>"

    with pytest.raises(NotSupported):
        assert resp.css("h1 ::text").get() == "World!"
    with pytest.raises(NotSupported):
        assert resp.xpath("//body/text()").getall() == ["Hello"]


@ensureDeferred
@pytest.mark.skipif(sys.version_info < (3, 8), reason="unittest.mock.AsyncMock")
@pytest.mark.filterwarnings("ignore:.*None is deprecated")
@pytest.mark.parametrize(
    "meta,settings,expected,use_zyte_api",
    [
        # Default ZYTE_API_ON_ALL_REQUESTS
        ({}, {}, {}, False),
        (
            {"zyte_api": {}},
            {},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": True},
            {},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        ({"zyte_api": False}, {}, {}, False),
        (
            {},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {},
            False,
        ),
        (
            {"zyte_api": False},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {},
            False,
        ),
        (
            {"zyte_api": None},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {},
            False,
        ),
        (
            {"zyte_api": {}},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": True},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": {"javascript": True, "geolocation": "US"}},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {
                "browserHtml": True,
                "geolocation": "US",
                "javascript": True,
                "httpResponseHeaders": True,
            },
            True,
        ),
        # ZYTE_API_ON_ALL_REQUESTS=False
        ({}, {"ZYTE_API_ON_ALL_REQUESTS": False}, {}, False),
        (
            {"zyte_api": {}},
            {"ZYTE_API_ON_ALL_REQUESTS": False},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": True},
            {"ZYTE_API_ON_ALL_REQUESTS": False},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        ({"zyte_api": False}, {"ZYTE_API_ON_ALL_REQUESTS": False}, {}, False),
        (
            {},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": False,
            },
            {},
            False,
        ),
        (
            {"zyte_api": False},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": False,
            },
            {},
            False,
        ),
        (
            {"zyte_api": None},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": False,
            },
            {},
            False,
        ),
        (
            {"zyte_api": {}},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": False,
            },
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": True},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": False,
            },
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": {"javascript": True, "geolocation": "US"}},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": False,
            },
            {
                "browserHtml": True,
                "geolocation": "US",
                "javascript": True,
                "httpResponseHeaders": True,
            },
            True,
        ),
        # ZYTE_API_ON_ALL_REQUESTS=True
        (
            {},
            {"ZYTE_API_ON_ALL_REQUESTS": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": {}},
            {"ZYTE_API_ON_ALL_REQUESTS": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": True},
            {"ZYTE_API_ON_ALL_REQUESTS": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            True,
        ),
        ({"zyte_api": False}, {"ZYTE_API_ON_ALL_REQUESTS": True}, {}, False),
        (
            {},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": True,
            },
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": False},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": True,
            },
            {},
            False,
        ),
        (
            {"zyte_api": None},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": True,
            },
            {},
            False,
        ),
        (
            {"zyte_api": {}},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": True,
            },
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": True},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": True,
            },
            {"browserHtml": True, "geolocation": "CA", "httpResponseHeaders": True},
            True,
        ),
        (
            {"zyte_api": {"javascript": True, "geolocation": "US"}},
            {
                "ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"},
                "ZYTE_API_ON_ALL_REQUESTS": True,
            },
            {
                "browserHtml": True,
                "geolocation": "US",
                "javascript": True,
                "httpResponseHeaders": True,
            },
            True,
        ),
    ],
)
async def test_zyte_api_request_meta(
    meta: Dict[str, Dict[str, Any]],
    settings: Dict[str, str],
    expected: Dict[str, str],
    use_zyte_api: bool,
    mockserver,
):
    async with mockserver.make_handler(settings) as handler:
        req = Request(mockserver.urljoin("/"), meta=meta)
        unmocked_client = handler._client
        handler._client = mock.AsyncMock(unmocked_client)
        handler._client.request_raw.side_effect = unmocked_client.request_raw

        await handler.download_request(req, None)

        # What we're interested in is the Request call in the API
        request_call = [
            c for c in handler._client.mock_calls if "request_raw(" in str(c)
        ]

        if not use_zyte_api:
            assert request_call == []
            return

        elif not request_call:
            pytest.fail("The client's request_raw() method was not called.")

        args_used = request_call[0].args[0]
        args_used.pop("url")

        assert args_used == expected


@ensureDeferred
async def test_disable(mockserver):
    settings = {"ZYTE_API_ENABLED": False}
    async with mockserver.make_handler(settings) as handler:
        assert handler is None


@ensureDeferred
@pytest.mark.skipif(sys.version_info < (3, 8), reason="unittest.mock.AsyncMock")
async def test_zyte_api_request_meta_none_deprecation(mockserver):
    async with mockserver.make_handler() as handler:
        req = Request(mockserver.urljoin("/"), meta={"zyte_api": None})
        handler._client = mock.AsyncMock(handler._client)
        with pytest.warns(DeprecationWarning, match="None is deprecated"):
            await handler.download_request(req, None)


@pytest.mark.parametrize(
    "meta",
    [
        {"zyte_api": {"waka": True}},
        {"zyte_api": True},
        {"zyte_api": {"browserHtml": True}},
        {"zyte_api": {}},
        {"zyte_api": False},
        {"randomParameter": True},
        {},
        None,
    ],
)
@ensureDeferred
async def test_coro_handling(meta: Dict[str, Dict[str, Any]], mockserver):
    settings = {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True}}
    async with mockserver.make_handler(settings) as handler:
        req = Request(
            # this should really be a URL to a website, not to the API server,
            # but API server URL works ok
            mockserver.urljoin("/"),
            meta=meta,
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
            "Got an error when processing Zyte API request (http://example.com): "
            "Object of type Request is not JSON serializable",
        ),
        (
            {"zyte_api": ["some", "bad", "non-dict", "value"]},
            ValueError,
            "'zyte_api' parameters in the request meta should be provided as "
            "dictionary, got <class 'list'> instead. (<POST http://example.com>).",
        ),
        (
            {"zyte_api": 1},
            TypeError,
            "'zyte_api' parameters in the request meta should be provided as "
            "dictionary, got <class 'int'> instead. (<POST http://example.com>).",
        ),
        (
            {"zyte_api": {"browserHtml": True, "httpResponseBody": True}},
            RequestError,
            "Got Zyte API error (status=422, type='/request/unprocessable') while processing URL (http://example.com): "
            "Incompatible parameters were found in the request.",
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

        with pytest.raises(exception_type):  # NOQA
            api_params = handler._prepare_api_params(req)
            await deferred_from_coro(
                handler._download_request(api_params, req, Spider("test"))  # NOQA
            )  # NOQA
        assert exception_text in caplog.text


@pytest.mark.parametrize(
    "job_id",
    ["547773/99/6"],
)
@ensureDeferred
async def test_job_id(job_id, mockserver):
    settings = {"JOB": job_id}
    async with mockserver.make_handler(settings) as handler:
        req = Request(
            "http://example.com",
            method="POST",
            meta={"zyte_api": {"browserHtml": True}},
        )
        api_params = handler._prepare_api_params(req)
        resp = await deferred_from_coro(
            handler._download_request(api_params, req, Spider("test"))  # NOQA
        )

    assert resp.request is req
    assert resp.url == req.url
    assert resp.status == 200
    assert "zyte-api" in resp.flags
    assert resp.body == f"<html>{job_id}</html>".encode("utf8")


@ensureDeferred
async def test_higher_concurrency():
    """Send DEFAULT_CLIENT_CONCURRENCY + 1 requests, the first and last taking
    less time than the rest, and ensure that the first 2 responses are the
    first and the last, verifying that a concurrency ≥
    DEFAULT_CLIENT_CONCURRENCY + 1 has been reached."""
    concurrency = DEFAULT_CLIENT_CONCURRENCY + 1
    response_indexes = []
    expected_first_indexes = {0, concurrency - 1}
    fast_seconds = 0.001
    slow_seconds = 0.1

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
                                    if index in expected_first_indexes
                                    else slow_seconds
                                ),
                            },
                        },
                        dont_filter=True,
                    )

            async def parse(self, response):
                response_indexes.append(response.meta["index"])

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

    assert (
        set(response_indexes[: len(expected_first_indexes)]) == expected_first_indexes
    )


@ensureDeferred
@pytest.mark.skipif(sys.version_info < (3, 8), reason="unittest.mock.AsyncMock")
@pytest.mark.parametrize(
    "request_kwargs,settings,expected,warnings",
    [
        # Automatic mapping of request parameters to Zyte Data API parameters
        # is enabled by default, but can be disabled.
        #
        # httpResponseBody is set to True if no other main content is
        # requested.
        *(
            (
                {},
                settings,
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                },
                [],
            )
            for settings in (
                {},
                {"ZYTE_API_AUTOMAP": True},
            )
        ),
        (
            {},
            {"ZYTE_API_AUTOMAP": False},
            False,
            [],
        ),
        *(
            (
                {"meta": {"zyte_api": {"a": "b"}}},
                settings,
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "a": "b",
                },
                [],
            )
            for settings in (
                {},
                {"ZYTE_API_AUTOMAP": True},
            )
        ),
        (
            {"meta": {"zyte_api": {"a": "b"}}},
            {"ZYTE_API_AUTOMAP": False},
            {
                "a": "b",
            },
            [],
        ),
        # httpResponseBody can be unset through meta. That way, if a new main
        # output type other than browserHtml and screenshot is implemented in
        # the future, you can request the new output type and also prevent
        # httpResponseBody from being enabled automatically, without the need
        # to disable automated mapping completely.
        (
            {"meta": {"zyte_api": {"httpResponseBody": False}}},
            {},
            {
                "httpResponseBody": False,
            },
            [],
        ),
        (
            {
                "meta": {
                    "zyte_api": {"httpResponseBody": False, "newOutputType": True}
                },
            },
            {},
            {
                "httpResponseBody": False,
                "newOutputType": True,
            },
            [],
        ),
        # httpResponseHeaders is automatically set to True for httpResponseBody
        # (shown in prior tests) and browserHtml.
        (
            {
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # httpResponseHeaders is not set for screenshot.
        (
            {
                "meta": {"zyte_api": {"screenshot": True}},
            },
            {},
            {
                "screenshot": True,
            },
            [],
        ),
        # httpResponseHeaders can be unset through meta.
        (
            {
                "meta": {"zyte_api": {"httpResponseHeaders": False}},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": False,
            },
            [],
        ),
        (
            {
                "meta": {
                    "zyte_api": {
                        "browserHtml": True,
                        "httpResponseHeaders": False,
                    },
                },
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": False,
            },
            [],
        ),
        # METHOD
        # Request.method is mapped as is.
        *(
            (
                {"method": method},
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
            )
        ),
        # Request.method is mapped even for methods that Zyte Data API does not
        # support.
        *(
            (
                {"method": method},
                {},
                {
                    "httpResponseBody": True,
                    "httpResponseHeaders": True,
                    "httpRequestMethod": method,
                },
                [],
            )
            for method in (
                "HEAD",
                "CONNECT",
                "FOO",
            )
        ),
        # An exception is the default method (GET), which is not mapped.
        (
            {"method": "GET"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # httpRequestMethod should not be defined through meta.
        (
            {
                "meta": {
                    "zyte_api": {
                        "httpRequestMethod": "GET",
                    },
                },
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestMethod": "GET",
            },
            ["Use Request.method instead"],
        ),
        # If defined through meta, httpRequestMethod takes precedence, warning
        # about value mismatches.
        (
            {
                "method": "POST",
                "meta": {
                    "zyte_api": {
                        "httpRequestMethod": "PATCH",
                    },
                },
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestMethod": "PATCH",
            },
            [
                "Use Request.method instead",
                "does not match the Zyte Data API httpRequestMethod parameter",
            ],
        ),
        # A non-GET method should not be used unless httpResponseBody is also
        # used.
        (
            {
                "method": "POST",
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["can only be set when the httpResponseBody parameter"],
        ),
        (
            {
                "method": "POST",
                "meta": {"zyte_api": {"screenshot": True}},
            },
            {},
            {
                "screenshot": True,
            },
            ["can only be set when the httpResponseBody parameter"],
        ),
        # HEADERS
        # Headers are mapped to requestHeaders or customHttpRequestHeaders
        # depending on whether or not httpResponseBody is declared.
        (
            {
                "headers": {"Referer": "a"},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
            },
            [],
        ),
        (
            {
                "headers": {"Referer": "a"},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        # We intentionally generate requestHeaders even if browserHtml and
        # screenshot are not used, assuming that future additional outputs are
        # more likely to use requestHeaders than to use
        # customHttpRequestHeaders.
        (
            {
                "headers": {"Referer": "a"},
                "meta": {"zyte_api": {"httpResponseBody": False}},
            },
            {},
            {
                "httpResponseBody": False,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        # If both httpResponseBody and currently-incompatible attributes
        # (browserHtml, screenshot) are declared, both fields are generated.
        # This is in case a single request is allowed to combine both in the
        # future.
        (
            {
                "headers": {"Referer": "a"},
                "meta": {
                    "zyte_api": {
                        "httpResponseBody": True,
                        "browserHtml": True,
                        # Makes the mock API server return 200 despite the
                        # bad input.
                        "passThrough": True,
                    },
                },
            },
            {},
            {
                "httpResponseBody": True,
                "browserHtml": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "requestHeaders": {"referer": "a"},
                "passThrough": True,
            },
            [],
        ),
        # If requestHeaders or customHttpRequestHeaders are used, their value
        # prevails, but a warning is issued.
        (
            {
                "headers": {"Referer": "a"},
                "meta": {
                    "zyte_api": {
                        "customHttpRequestHeaders": [
                            {"name": "Referer", "value": "b"},
                        ],
                    },
                },
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "b"},
                ],
            },
            ["Use Request.headers instead"],
        ),
        (
            {
                "headers": {"Referer": "a"},
                "meta": {
                    "zyte_api": {
                        "browserHtml": True,
                        "requestHeaders": {"referer": "b"},
                    },
                },
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "b"},
            },
            ["Use Request.headers instead"],
        ),
        # A request should not have headers if requestHeaders or
        # customHttpRequestHeaders are also used, even if they match.
        (
            {
                "headers": {"Referer": "b"},
                "meta": {
                    "zyte_api": {
                        "customHttpRequestHeaders": [
                            {"name": "Referer", "value": "b"},
                        ],
                    },
                },
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "b"},
                ],
            },
            ["Use Request.headers instead"],
        ),
        (
            {
                "headers": {"Referer": "b"},
                "meta": {
                    "zyte_api": {
                        "browserHtml": True,
                        "requestHeaders": {"referer": "b"},
                    },
                },
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "b"},
            },
            ["Use Request.headers instead"],
        ),
        # Unsupported headers not present in Scrapy requests by default are
        # dropped with a warning.
        # If all headers are unsupported, the header parameter is not even set.
        (
            {
                "headers": {"a": "b"},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # Headers with None as value are silently ignored.
        (
            {
                "headers": {"a": None},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        # Headers with an empty string as value are not silently ignored.
        (
            {
                "headers": {"a": ""},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # Unsupported headers are looked up case-insensitively.
        (
            {
                "headers": {"user-Agent": ""},
            },
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
                "headers": DEFAULT_REQUEST_HEADERS,
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {
                "headers": {
                    "Accept": "application/json",
                    "Accept-Language": "uk",
                },
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # The Cookie header is dropped with a warning.
        (
            {
                "headers": {
                    "Cookie": "a=b",
                },
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        (
            {
                "headers": {
                    "Cookie": "a=b",
                },
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # The User-Agent header, which Scrapy sets by default, is dropped
        # silently if it matches the default value of the USER_AGENT setting,
        # or with a warning otherwise.
        (
            {
                "headers": {"User-Agent": DEFAULT_USER_AGENT},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {
                "headers": {"User-Agent": ""},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        (
            {
                "headers": {"User-Agent": DEFAULT_USER_AGENT},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {
                "headers": {"User-Agent": ""},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # You may update the ZYTE_API_UNSUPPORTED_HEADERS setting to remove
        # headers that the customHttpRequestHeaders parameter starts supporting
        # in the future.
        (
            {
                "headers": {
                    "Cookie": "",
                    "User-Agent": "",
                },
            },
            {
                "ZYTE_API_UNSUPPORTED_HEADERS": ["Cookie"],
            },
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "customHttpRequestHeaders": [
                    {"name": "User-Agent", "value": ""},
                ],
            },
            [
                "defines header b'Cookie', which cannot be mapped",
            ],
        ),
        # You may update the ZYTE_API_BROWSER_HEADERS setting to extend support
        # for new fields that the requestHeaders parameter may support in the
        # future.
        (
            {
                "headers": {"User-Agent": ""},
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {
                "ZYTE_API_BROWSER_HEADERS": {
                    "Referer": "referer",
                    "User-Agent": "userAgent",
                },
            },
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"userAgent": ""},
            },
            [],
        ),
        # BODY
        # The body is copied into httpRequestBody, base64-encoded.
        (
            {
                "body": "a",
            },
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
            {
                "body": "a",
                "meta": {"zyte_api": {"httpRequestBody": "Yg=="}},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestBody": "Yg==",
            },
            [
                "Use Request.body instead",
                "does not match the Zyte Data API httpRequestBody parameter",
            ],
        ),
        # httpRequestBody defined in meta causes a warning even if it matches
        # request.body.
        (
            {
                "body": "a",
                "meta": {"zyte_api": {"httpRequestBody": "YQ=="}},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "httpRequestBody": "YQ==",
            },
            ["Use Request.body instead"],
        ),
        # A body should not be used unless httpResponseBody is also used.
        (
            {
                "body": "a",
                "meta": {"zyte_api": {"browserHtml": True}},
            },
            {},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["can only be set when the httpResponseBody parameter"],
        ),
        (
            {
                "body": "a",
                "meta": {"zyte_api": {"screenshot": True}},
            },
            {},
            {
                "screenshot": True,
            },
            ["can only be set when the httpResponseBody parameter"],
        ),
        # httpResponseHeaders
        # Warn if httpResponseHeaders is defined unnecessarily.
        (
            {
                "meta": {"zyte_api": {"httpResponseHeaders": True}},
            },
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["do not need to set httpResponseHeaders"],
        ),
    ],
)
async def test_automap(
    request_kwargs: Dict[str, Any],
    settings: Dict[str, Any],
    expected: Union[Dict[str, str], Literal[False]],
    warnings: List[str],
    mockserver,
    caplog,
):
    settings.update({"ZYTE_API_ON_ALL_REQUESTS": True})
    async with mockserver.make_handler(settings) as handler:
        if expected is False:
            # Only the Zyte Data API client is mocked, meaning requests that
            # do not go through Zyte Data API are actually sent, so we point
            # them to the mock server to avoid internet connections in tests.
            request_kwargs["url"] = mockserver.urljoin("/")
        else:
            request_kwargs["url"] = "https://toscrape.com"
        request = Request(**request_kwargs)
        unmocked_client = handler._client
        handler._client = mock.AsyncMock(unmocked_client)
        handler._client.request_raw.side_effect = unmocked_client.request_raw
        with caplog.at_level("WARNING"):
            await handler.download_request(request, None)

        # What we're interested in is the Request call in the API
        request_call = [
            c for c in handler._client.mock_calls if "request_raw(" in str(c)
        ]

        if expected is False:
            assert request_call == []
            return

        if not request_call:
            pytest.fail("The client's request_raw() method was not called.")

        args_used = request_call[0].args[0]
        args_used.pop("url")
        assert args_used == expected

        if warnings:
            for warning in warnings:
                assert warning in caplog.text
        else:
            assert not caplog.records
