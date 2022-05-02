import os
from asyncio import iscoroutine
from typing import Any, Dict

import pytest
from _pytest.logging import LogCaptureFixture  # NOQA
from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Response, TextResponse
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
    async def produce_request_response(meta):
        with MockServer() as server:
            async with make_handler({}, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta=meta,
                )
                coro = handler._download_request(req, Spider("test"))
                assert iscoroutine(coro)
                assert not isinstance(coro, Deferred)
                resp = await coro  # type: ignore
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
    @pytest.mark.asyncio
    async def test_browser_html_request(self, meta: Dict[str, Dict[str, Any]]):
        req, resp = await self.produce_request_response(meta)
        assert isinstance(resp, TextResponse)
        assert resp.request is req
        assert resp.url == req.url
        assert resp.status == 200
        assert "zyte-api" in resp.flags
        assert resp.body == b"<html></html>"
        assert resp.text == "<html></html>"

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
    @pytest.mark.asyncio
    async def test_http_response_body_request(self, meta: Dict[str, Dict[str, Any]]):
        req, resp = await self.produce_request_response(meta)
        assert isinstance(resp, Response)
        assert resp.request is req
        assert resp.url == req.url
        assert resp.status == 200
        assert "zyte-api" in resp.flags
        assert resp.body == b"<html></html>"

    @pytest.mark.parametrize(
        "meta",
        [
            {"zyte_api": {"httpResponseBody": True, "httpResponseHeaders": True}},
            {"zyte_api": {"browserHtml": True, "httpResponseHeaders": True}},
        ],
    )
    @pytest.mark.asyncio
    async def test_http_response_headers_request(self, meta: Dict[str, Dict[str, Any]]):
        req, resp = await self.produce_request_response(meta)
        assert resp.request is req
        assert resp.url == req.url
        assert resp.status == 200
        assert "zyte-api" in resp.flags
        assert resp.body == b"<html></html>"
        assert resp.headers == {b"Test_Header": [b"test_value"]}

    @pytest.mark.parametrize(
        "meta, api_relevant",
        [
            ({"zyte_api": {"waka": True}}, True),
            ({"zyte_api": True}, True),
            ({"zyte_api": {"browserHtml": True}}, True),
            ({"zyte_api": {}}, False),
            ({"randomParameter": True}, False),
            ({}, False),
        ],
    )
    @pytest.mark.asyncio
    async def test_coro_handling(
        self, meta: Dict[str, Dict[str, Any]], api_relevant: bool
    ):
        with MockServer() as server:
            async with make_handler({}, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta=meta,
                )
                if api_relevant:
                    coro = handler.download_request(req, Spider("test"))
                    assert not iscoroutine(coro)
                    assert isinstance(coro, Deferred)
                else:
                    # Non-API requests won't get into handle, but run HTTPDownloadHandler.download_request instead
                    # But because they're Deffered - they won't run because event loop is closed
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
                {"zyte_api": True},
                "/",
                IgnoreRequest,
                "zyte_api parameters in the request meta should be provided as "
                "dictionary, got <class 'bool'> instead (http://example.com)",
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
    @pytest.mark.asyncio
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
                with pytest.raises(exception_type):  # NOQA
                    await handler._download_request(req, Spider("test"))  # NOQA
                assert exception_text in caplog.text

    @pytest.mark.parametrize(
        "job_id",
        ["547773/99/6"],
    )
    @pytest.mark.asyncio
    async def test_job_id(self, job_id):
        with MockServer() as server:
            async with make_handler({"JOB": job_id}, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta={"zyte_api": {"browserHtml": True}},
                )
                resp = await handler._download_request(req, Spider("test"))  # NOQA

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
