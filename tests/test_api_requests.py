import sys
from asyncio import iscoroutine
from typing import Any, Dict, List, Union
from unittest import mock
from unittest.mock import patch

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.http import Response, TextResponse
from scrapy.settings.default_settings import DEFAULT_REQUEST_HEADERS
from scrapy.settings.default_settings import USER_AGENT as DEFAULT_USER_AGENT
from scrapy.utils.test import get_crawler
from twisted.internet.defer import Deferred
from typing_extensions import Literal
from zyte_api.aio.errors import RequestError

from scrapy_zyte_api.handler import _get_api_params

from . import DEFAULT_CLIENT_CONCURRENCY, SETTINGS
from .mockserver import DelayedResource, MockServer, produce_request_response


@pytest.mark.parametrize(
    "meta",
    [
        {
            "httpResponseBody": True,
            "httpResponseHeaders": False,
            "customHttpRequestHeaders": {"Accept": "application/octet-stream"},
        },
        pytest.param(
            {
                "httpResponseBody": True,
                "customHttpRequestHeaders": {"Accept": "application/octet-stream"},
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
        {"browserHtml": True},
        {"browserHtml": True, "httpResponseHeaders": False},
        {"httpResponseBody": True},
        pytest.param(
            {"httpResponseBody": True, "httpResponseHeaders": False},
            marks=pytest.mark.xfail(
                reason="https://github.com/scrapy-plugins/scrapy-zyte-api/issues/47",
                strict=True,
            ),
        ),
    ],
)
async def test_response_html(meta: Dict[str, Dict[str, Any]], mockserver):
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
    if meta.get("httpResponseHeaders", True) is True:
        assert resp.headers == {b"Test_Header": [b"test_value"]}
    else:
        assert not resp.headers


@ensureDeferred
async def test_disable(mockserver):
    settings = {"ZYTE_API_ENABLED": False}
    async with mockserver.make_handler(settings) as handler:
        assert handler is None


@pytest.mark.parametrize("zyte_api", [True, False])
@ensureDeferred
async def test_coro_handling(zyte_api: bool, mockserver):
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
        with pytest.raises(exception_type):
            await handler.download_request(req, None)
        assert exception_text in caplog.text


@ensureDeferred
async def test_job_id(mockserver):
    job_id = "547773/99/6"
    settings = {"JOB": job_id}
    async with mockserver.make_handler(settings) as handler:
        req = Request(
            "http://example.com",
            method="POST",
            meta={"zyte_api": {"browserHtml": True}},
        )
        resp = await handler.download_request(req, None)

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


AUTOMAP_BY_DEFAULT = True
BROWSER_HEADERS = {b"referer": "referer"}
DEFAULT_PARAMS: Dict[str, Any] = {}
UNSUPPORTED_HEADERS = {b"cookie", b"user-agent"}
USE_API_BY_DEFAULT = False


@ensureDeferred
async def test_get_api_params_input_default(mockserver):
    request = Request(url="https://example.com")
    async with mockserver.make_handler() as handler:
        patch_path = "scrapy_zyte_api.handler._get_api_params"
        with patch(patch_path) as _get_api_params:
            _get_api_params.side_effect = RuntimeError("That’s it!")
            with pytest.raises(RuntimeError):
                await handler.download_request(request, None)
            _get_api_params.assert_called_once_with(
                request,
                use_api_by_default=USE_API_BY_DEFAULT,
                automap_by_default=AUTOMAP_BY_DEFAULT,
                default_params=DEFAULT_PARAMS,
                unsupported_headers=UNSUPPORTED_HEADERS,
                browser_headers=BROWSER_HEADERS,
            )


@ensureDeferred
async def test_get_api_params_input_custom(mockserver):
    request = Request(url="https://example.com")
    settings = {
        "ZYTE_API_AUTOMAP": False,
        "ZYTE_API_BROWSER_HEADERS": {"B": "b"},
        "ZYTE_API_DEFAULT_PARAMS": {"a": "b"},
        "ZYTE_API_ON_ALL_REQUESTS": True,
        "ZYTE_API_UNSUPPORTED_HEADERS": {"A"},
    }
    async with mockserver.make_handler(settings) as handler:
        patch_path = "scrapy_zyte_api.handler._get_api_params"
        with patch(patch_path) as _get_api_params:
            _get_api_params.side_effect = RuntimeError("That’s it!")
            with pytest.raises(RuntimeError):
                await handler.download_request(request, None)
            _get_api_params.assert_called_once_with(
                request,
                use_api_by_default=True,
                automap_by_default=False,
                default_params={"a": "b"},
                unsupported_headers={b"a"},
                browser_headers={b"b": "b"},
            )


UNSET = object()


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
        (False, {"zyte_api": {"browserHtml": True}}, {"browserHtml": True}),
        (True, None, {}),
        (True, {}, {}),
        (True, {"a": "b"}, {}),
        (True, {"zyte_api": False}, None),
        (True, {"zyte_api": True}, {}),
        (True, {"zyte_api": {}}, {}),
        (True, {"zyte_api": {"a": "b"}}, {"a": "b"}),
        (True, {"zyte_api": {"browserHtml": True}}, {"browserHtml": True}),
    ],
)
def test_api_toggling(setting, meta, expected):
    request = Request(url="https://example.com", meta=meta)
    api_params = _get_api_params(
        request,
        use_api_by_default=setting,
        automap_by_default=False,
        default_params=DEFAULT_PARAMS,
        unsupported_headers=UNSUPPORTED_HEADERS,
        browser_headers=BROWSER_HEADERS,
    )
    assert api_params == expected


@pytest.mark.parametrize("setting", [False, True])
@pytest.mark.parametrize("meta", [None, 0, "", b"", []])
def test_api_disabling_deprecated(setting, meta):
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = meta
    with pytest.warns(DeprecationWarning, match=r".* Use False instead\.$"):
        api_params = _get_api_params(
            request,
            use_api_by_default=setting,
            automap_by_default=False,
            default_params=DEFAULT_PARAMS,
            unsupported_headers=UNSUPPORTED_HEADERS,
            browser_headers=BROWSER_HEADERS,
        )
    assert api_params is None


@ensureDeferred
async def test_default_params_none(mockserver, caplog):
    request = Request(url="https://example.com")
    settings = {
        "ZYTE_API_DEFAULT_PARAMS": {"a": None, "b": "c"},
    }
    with caplog.at_level("WARNING"):
        async with mockserver.make_handler(settings) as handler:
            patch_path = "scrapy_zyte_api.handler._get_api_params"
            with patch(patch_path) as _get_api_params:
                _get_api_params.side_effect = RuntimeError("That’s it!")
                with pytest.raises(RuntimeError):
                    await handler.download_request(request, None)
                _get_api_params.assert_called_once_with(
                    request,
                    use_api_by_default=USE_API_BY_DEFAULT,
                    automap_by_default=AUTOMAP_BY_DEFAULT,
                    default_params={"b": "c"},
                    unsupported_headers=UNSUPPORTED_HEADERS,
                    browser_headers=BROWSER_HEADERS,
                )
    assert "Parameter 'a' in the ZYTE_API_DEFAULT_PARAMS setting is None" in caplog.text


@pytest.mark.parametrize(
    "default_params,meta,expected,warnings",
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
def test_default_params_merging(default_params, meta, expected, warnings, caplog):
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = meta
    with caplog.at_level("WARNING"):
        api_params = _get_api_params(
            request,
            use_api_by_default=USE_API_BY_DEFAULT,
            automap_by_default=False,
            default_params=default_params,
            unsupported_headers=UNSUPPORTED_HEADERS,
            browser_headers=BROWSER_HEADERS,
        )
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records


@pytest.mark.xfail(reason="To be implemented", strict=True)
@pytest.mark.parametrize(
    "default_params,meta,expected,warnings",
    [
        (
            {"screenshot": True, "httpResponseHeaders": True},
            {"browserHtml": True},
            {"browserHtml": True, "httpResponseHeaders": True, "screenshot": True},
            [],
        ),
        (
            {"browserHtml": True, "httpResponseHeaders": False},
            {"screenshot": True, "browserHtml": False},
            {"screenshot": True},
            [],
        ),
    ],
)
def test_default_params_automap(default_params, meta, expected, warnings, caplog):
    """Warnings about unneeded parameters should not apply if those parameters are needed to extend or override default parameters."""
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = meta
    with caplog.at_level("WARNING"):
        api_params = _get_api_params(
            request,
            use_api_by_default=USE_API_BY_DEFAULT,
            automap_by_default=AUTOMAP_BY_DEFAULT,
            default_params=default_params,
            unsupported_headers=UNSUPPORTED_HEADERS,
            browser_headers=BROWSER_HEADERS,
        )
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records


def test_default_params_immutability():
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = {"a": None}
    default_params = {"a": "b"}
    _get_api_params(
        request,
        use_api_by_default=USE_API_BY_DEFAULT,
        automap_by_default=AUTOMAP_BY_DEFAULT,
        default_params=default_params,
        unsupported_headers=UNSUPPORTED_HEADERS,
        browser_headers=BROWSER_HEADERS,
    )
    assert default_params == {"a": "b"}


@pytest.mark.parametrize("meta", [1, ["a", "b"]])
def test_bad_meta_type(meta):
    request = Request(url="https://example.com")
    request.meta["zyte_api"] = meta
    with pytest.raises(ValueError):
        _get_api_params(
            request,
            use_api_by_default=USE_API_BY_DEFAULT,
            automap_by_default=False,
            default_params=DEFAULT_PARAMS,
            unsupported_headers=UNSUPPORTED_HEADERS,
            browser_headers=BROWSER_HEADERS,
        )


@pytest.mark.parametrize(
    "setting,meta,expected",
    [
        (False, UNSET, False),
        (False, False, False),
        (False, True, True),
        (True, UNSET, True),
        (True, False, False),
        (True, True, True),
    ],
)
def test_automap_toggling(setting, meta, expected):
    request = Request(url="https://example.com")
    if meta is not UNSET:
        request.meta["zyte_api_automap"] = meta
    api_params = _get_api_params(
        request,
        use_api_by_default=True,
        automap_by_default=setting,
        default_params=DEFAULT_PARAMS,
        unsupported_headers=UNSUPPORTED_HEADERS,
        browser_headers=BROWSER_HEADERS,
    )
    assert bool(api_params) == expected


def _test_automap(request_kwargs, meta, expected, warnings, caplog):
    request = Request(url="https://example.com", **request_kwargs)
    request.meta["zyte_api"] = meta
    with caplog.at_level("WARNING"):
        api_params = _get_api_params(
            request,
            use_api_by_default=USE_API_BY_DEFAULT,
            automap_by_default=AUTOMAP_BY_DEFAULT,
            default_params=DEFAULT_PARAMS,
            unsupported_headers=UNSUPPORTED_HEADERS,
            browser_headers=BROWSER_HEADERS,
        )
    assert api_params == expected
    if warnings:
        for warning in warnings:
            assert warning in caplog.text
    else:
        assert not caplog.records


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        ({}, {"httpResponseBody": True, "httpResponseHeaders": True}, []),
        (
            {"httpResponseBody": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            ["do not need to set httpResponseBody to True"],
        ),
        (
            {"httpResponseBody": False},
            {},
            [],
        ),
        (
            {"httpResponseBody": True, "browserHtml": True},
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
        (
            {"browserHtml": True},
            {"browserHtml": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {"screenshot": True},
            {"screenshot": True},
            [],
        ),
        (
            {"unknown": True},
            {"httpResponseBody": True, "httpResponseHeaders": True, "unknown": True},
            [],
        ),
        (
            {"unknown": True, "httpResponseBody": False},
            {"unknown": True},
            [],
        ),
    ],
)
def test_automap_main_outputs(meta, expected, warnings, caplog):
    _test_automap({}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        ({"httpResponseHeaders": False}, {"httpResponseBody": True}, []),
        (
            {"httpResponseHeaders": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            ["do not need to set httpResponseHeaders to True"],
        ),
        (
            {"httpResponseBody": True, "httpResponseHeaders": False},
            {"httpResponseBody": True},
            ["do not need to set httpResponseBody to True"],
        ),
        (
            {"httpResponseBody": True, "httpResponseHeaders": True},
            {"httpResponseBody": True, "httpResponseHeaders": True},
            [
                "do not need to set httpResponseHeaders to True",
                "do not need to set httpResponseBody to True",
            ],
        ),
        (
            {"httpResponseBody": False, "httpResponseHeaders": False},
            {},
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {"httpResponseBody": False, "httpResponseHeaders": True},
            {"httpResponseHeaders": True},
            [],
        ),
        (
            {"browserHtml": True, "httpResponseHeaders": False},
            {"browserHtml": True},
            [],
        ),
        (
            {"browserHtml": True, "httpResponseHeaders": True},
            {"browserHtml": True, "httpResponseHeaders": True},
            ["do not need to set httpResponseHeaders to True"],
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
            {
                "httpResponseBody": True,
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            {
                "browserHtml": True,
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["do not need to set httpResponseHeaders to True"],
        ),
        (
            {"screenshot": True, "httpResponseHeaders": False},
            {"screenshot": True},
            ["do not need to set httpResponseHeaders to False"],
        ),
        (
            {"screenshot": True, "httpResponseHeaders": True},
            {"screenshot": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {"unknown": True, "httpResponseHeaders": True},
            {"unknown": True, "httpResponseBody": True, "httpResponseHeaders": True},
            ["do not need to set httpResponseHeaders to True"],
        ),
        (
            {"unknown": True, "httpResponseHeaders": False},
            {"unknown": True, "httpResponseBody": True},
            [],
        ),
        (
            {"unknown": True, "httpResponseBody": False, "httpResponseHeaders": True},
            {"unknown": True, "httpResponseHeaders": True},
            [],
        ),
        (
            {"unknown": True, "httpResponseBody": False, "httpResponseHeaders": False},
            {"unknown": True},
            ["do not need to set httpResponseHeaders to False"],
        ),
    ],
)
def test_automap_header_output(meta, expected, warnings, caplog):
    _test_automap({}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "method,meta,expected,warnings",
    [
        (
            "GET",
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            [],
        ),
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
                    "does not match the Zyte Data API httpRequestMethod",
                ],
            )
            for request_method, meta_method in (
                ("GET", "POST"),
                ("PUT", "GET"),
            )
        ),
        (
            "POST",
            {"browserHtml": True},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["can only be set when the httpResponseBody parameter"],
        ),
        (
            "POST",
            {"screenshot": True},
            {
                "screenshot": True,
            },
            ["can only be set when the httpResponseBody parameter"],
        ),
    ],
)
def test_automap_method(method, meta, expected, warnings, caplog):
    _test_automap({"method": method}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "headers,meta,expected,warnings",
    [
        # Base header mapping scenarios for a supported header.
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
        (
            {"Referer": "a"},
            {"browserHtml": True},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
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
            {"screenshot": True},
            {
                "screenshot": True,
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"screenshot": True, "httpResponseBody": True},
            {
                "screenshot": True,
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
            {"unknown": True},
            {
                "customHttpRequestHeaders": [
                    {"name": "Referer", "value": "a"},
                ],
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "unknown": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"unknown": True, "httpResponseBody": False},
            {
                "requestHeaders": {"referer": "a"},
                "unknown": True,
            },
            [],
        ),
        (
            {"Referer": "a"},
            {"httpResponseBody": False},
            {
                "requestHeaders": {"referer": "a"},
            },
            [],
        ),
        # Headers with None as value are ignored.
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
                "httpResponseHeaders": True,
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
            {"unknown": True},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "unknown": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"unknown": True, "httpResponseBody": False},
            {
                "unknown": True,
            },
            [],
        ),
        (
            {"Referer": None},
            {"httpResponseBody": False},
            {},
            [],
        ),
        # Warn if header parameters are used, even if the values match request
        # headers.
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
                "httpResponseHeaders": True,
            },
            ["Use Request.headers instead"],
        ),
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
                "httpResponseHeaders": True,
            },
            ["Use Request.headers instead"],
        ),
        # Unsupported headers not present in Scrapy requests by default are
        # dropped with a warning.
        # If all headers are unsupported, the header parameter is not even set.
        (
            {"Cookie": "a=b"},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        (
            {"a": "b"},
            {"browserHtml": True},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        # Headers with an empty string as value are not silently ignored.
        (
            {"Cookie": ""},
            {},
            {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
            },
            ["cannot be mapped"],
        ),
        (
            {"a": ""},
            {"browserHtml": True},
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
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
    ],
)
def test_automap_headers(headers, meta, expected, warnings, caplog):
    _test_automap({"headers": headers}, meta, expected, warnings, caplog)


@pytest.mark.parametrize(
    "meta,expected,warnings",
    [
        (
            {
                "httpResponseBody": False,
            },
            {},
            [],
        ),
        (
            {
                "browserHtml": True,
                "httpResponseBody": False,
            },
            {
                "browserHtml": True,
                "httpResponseHeaders": True,
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
            },
            {
                "httpResponseBody": True,
            },
            [],
        ),
    ],
)
def test_automap_default_parameter_cleanup(meta, expected, warnings, caplog):
    _test_automap({}, meta, expected, warnings, caplog)
