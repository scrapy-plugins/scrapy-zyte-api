import os
import sys
from asyncio import iscoroutine
from typing import Any, Dict
from unittest import mock

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest, NotConfigured, NotSupported
from scrapy.http import Response, TextResponse
from scrapy.utils.defer import deferred_to_future
from scrapy.utils.test import get_crawler
from twisted.internet.asyncioreactor import install as install_asyncio_reactor
from twisted.internet.defer import Deferred
from twisted.internet.error import ReactorAlreadyInstalledError

from tests import make_handler
from tests.mockserver import MockServer

try:
    install_asyncio_reactor()
except ReactorAlreadyInstalledError:
    pass
os.environ["ZYTE_API_KEY"] = "test"


class TestAPI:
    @staticmethod
    async def produce_request_response(meta, custom_settings=None):
        with MockServer() as server:
            async with make_handler(custom_settings, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta=meta,
                )
                coro_or_deferred = handler.download_request(req, None)
                if iscoroutine(coro_or_deferred):
                    resp = await coro_or_deferred  # type: ignore
                else:
                    resp = await deferred_to_future(coro_or_deferred)

                return req, resp

    @pytest.mark.parametrize(
        "meta",
        [
            {"zyte_api": {"browserHtml": True}},
            {"zyte_api": {"browserHtml": True, "geolocation": "US"}},
            {"zyte_api": {"browserHtml": True, "geolocation": "US", "echoData": 123}},
            {"zyte_api": {"browserHtml": True, "randomParameter": None}},
        ],
    )
    async def test_browser_html_request(self, meta: Dict[str, Dict[str, Any]]):
        req, resp = await self.produce_request_response(meta)
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
    async def test_http_response_body_request(self, meta: Dict[str, Dict[str, Any]]):
        req, resp = await self.produce_request_response(meta)
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
    async def test_http_response_headers_request(self, meta: Dict[str, Dict[str, Any]]):
        req, resp = await self.produce_request_response(meta)
        assert resp.request is req
        assert resp.url == req.url
        assert resp.status == 200
        assert "zyte-api" in resp.flags
        assert resp.body == b"<html><body>Hello<h1>World!</h1></body></html>"
        assert resp.headers == {b"Test_Header": [b"test_value"]}

    @pytest.mark.skipif(
        sys.version_info < (3, 8), reason="Python3.7 has poor support for AsyncMocks"
    )
    @pytest.mark.parametrize(
        "meta,custom_settings,expected,use_zyte_api",
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
    @mock.patch("tests.AsyncClient")
    async def test_zyte_api_request_meta(
        self,
        mock_client,
        meta: Dict[str, Dict[str, Any]],
        custom_settings: Dict[str, str],
        expected: Dict[str, str],
        use_zyte_api: bool,
    ):
        try:
            # This would always error out since the mocked client doesn't
            # return the expected API response.
            await self.produce_request_response(meta, custom_settings=custom_settings)
        except Exception:
            pass

        # What we're interested in is the Request call in the API
        request_call = [c for c in mock_client.mock_calls if "request_raw(" in str(c)]

        if not use_zyte_api:
            assert request_call == []
            return

        elif not request_call:
            pytest.fail("The client's request_raw() method was not called.")

        args_used = request_call[0].args[0]
        args_used.pop("url")

        assert args_used == expected

    @pytest.mark.parametrize(
        "meta, api_relevant",
        [
            ({"zyte_api": {"waka": True}}, True),
            ({"zyte_api": True}, True),
            ({"zyte_api": {"browserHtml": True}}, True),
            ({"zyte_api": {}}, True),
            ({"zyte_api": None}, False),
            ({"randomParameter": True}, False),
            ({}, False),
            (None, False),
        ],
    )
    async def test_coro_handling(
        self, meta: Dict[str, Dict[str, Any]], api_relevant: bool
    ):
        custom_settings = {"ZYTE_API_DEFAULT_PARAMS": {"browserHtml": True}}
        with MockServer() as server:
            async with make_handler({}, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta=meta,
                )
                handler._zyte_api_default_params = custom_settings
                if api_relevant:
                    coro = handler.download_request(req, Spider("test"))
                    assert not iscoroutine(coro)
                    assert isinstance(coro, Deferred)
                else:
                    # Non-API requests won't get into handle, but run HTTPDownloadHandler.download_request instead
                    # But because they're Deferred - they won't run because event loop is closed
                    with pytest.raises(RuntimeError, match="Event loop is closed"):
                        handler.download_request(req, Spider("test"))

    @pytest.mark.parametrize(
        "meta, server_path, exception_type, exception_text",
        [
            (
                {"zyte_api": {"echoData": Request("http://test.com")}},
                "/",
                IgnoreRequest,
                "Got an error when processing Zyte API request (http://example.com): "
                "Object of type Request is not JSON serializable",
            ),
            (
                {"zyte_api": {"browserHtml": True}},
                "/exception/",
                IgnoreRequest,
                "Got Zyte API error (400) while processing URL (http://example.com): "
                "Bad Request",
            ),
        ],
    )
    async def test_exceptions(
        self,
        caplog: LogCaptureFixture,
        meta: Dict[str, Dict[str, Any]],
        server_path: str,
        exception_type: Exception,
        exception_text: str,
    ):
        with MockServer() as server:
            async with make_handler({}, server.urljoin(server_path)) as handler:
                req = Request("http://example.com", method="POST", meta=meta)
                api_params = handler._prepare_api_params(req)

                with pytest.raises(exception_type):  # NOQA
                    await handler._download_request(
                        api_params, req, Spider("test")
                    )  # NOQA
                assert exception_text in caplog.text

    @pytest.mark.parametrize(
        "job_id",
        ["547773/99/6"],
    )
    async def test_job_id(self, job_id):
        with MockServer() as server:
            async with make_handler({"JOB": job_id}, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta={"zyte_api": {"browserHtml": True}},
                )
                api_params = handler._prepare_api_params(req)
                resp = await handler._download_request(
                    api_params, req, Spider("test")
                )  # NOQA

            assert resp.request is req
            assert resp.url == req.url
            assert resp.status == 200
            assert "zyte-api" in resp.flags
            assert resp.body == f"<html>{job_id}</html>".encode("utf8")


def test_api_key_presence():
    from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler

    API_KEY = "TEST_API_KEY"

    # Setting the API KEY via env vars should work
    os.environ["ZYTE_API_KEY"] = API_KEY
    crawler = get_crawler(settings_dict={})
    handler = ScrapyZyteAPIDownloadHandler.from_crawler(crawler)
    assert handler._client.api_key == API_KEY

    # Having the API KEY missing in both env vars and Scrapy Settings should
    # error out.
    os.environ["ZYTE_API_KEY"] = ""
    crawler = get_crawler(settings_dict={})
    with pytest.raises(NotConfigured):
        ScrapyZyteAPIDownloadHandler.from_crawler(crawler)

    # Setting the API KEY via Scrapy settings should work
    crawler = get_crawler(settings_dict={"ZYTE_API_KEY": API_KEY})
    handler = ScrapyZyteAPIDownloadHandler.from_crawler(crawler)
    assert handler._client.api_key == API_KEY
