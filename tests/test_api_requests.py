import sys
from asyncio import iscoroutine
from typing import Any, Dict
from unittest import mock

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest, NotSupported
from scrapy.http import Response, TextResponse
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
    ],
)
async def test_browser_html_request(meta: Dict[str, Dict[str, Any]], mockserver):
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


@pytest.mark.parametrize(
    "meta",
    [
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


@pytest.mark.parametrize(
    "meta",
    [
        {"zyte_api": {"httpResponseBody": True, "httpResponseHeaders": True}},
        {"zyte_api": {"browserHtml": True, "httpResponseHeaders": True}},
    ],
)
@ensureDeferred
async def test_http_response_headers_request(meta: Dict[str, Dict[str, Any]], mockserver):
    req, resp = await produce_request_response(mockserver, meta)
    assert resp.request is req
    assert resp.url == req.url
    assert resp.status == 200
    assert "zyte-api" in resp.flags
    assert resp.body == b"<html><body>Hello<h1>World!</h1></body></html>"
    assert resp.headers == {b"Test_Header": [b"test_value"]}


@ensureDeferred
@pytest.mark.skipif(sys.version_info < (3, 8), reason="unittest.mock.AsyncMock")
@pytest.mark.parametrize(
    "meta,settings,expected,use_zyte_api",
    [
        ({}, {}, {}, False),
        ({"zyte_api": {}}, {}, {}, False),
        ({"zyte_api": True}, {}, {}, False),
        ({"zyte_api": False}, {}, {}, False),
        (
            {},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {"browserHtml": True, "geolocation": "CA"},
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
            {"browserHtml": True, "geolocation": "CA"},
            True,
        ),
        (
            {"zyte_api": True},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {"browserHtml": True, "geolocation": "CA"},
            True,
        ),
        (
            {"zyte_api": {"javascript": True, "geolocation": "US"}},
            {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True, "geolocation": "CA"}},
            {"browserHtml": True, "geolocation": "US", "javascript": True},
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


@pytest.mark.parametrize(
    "meta",
    [
        {"zyte_api": {"waka": True}},
        {"zyte_api": True},
        {"zyte_api": {"browserHtml": True}},
        {"zyte_api": {}},
        {"zyte_api": None},
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
            IgnoreRequest,
            "Got an error when processing Zyte API request (http://example.com): "
            "Object of type Request is not JSON serializable",
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
        api_params = handler._prepare_api_params(req)

        with pytest.raises(exception_type):  # NOQA
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
