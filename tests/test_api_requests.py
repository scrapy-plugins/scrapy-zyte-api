import os

import pytest
from _pytest.logging import LogCaptureFixture
from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest
from twisted.internet.asyncioreactor import install as install_asyncio_reactor
from twisted.internet.error import ReactorAlreadyInstalledError

from tests import make_handler
from tests.mockserver import MockServer

try:
    install_asyncio_reactor()
except ReactorAlreadyInstalledError:
    pass
os.environ["ZYTE_API_KEY"] = "test"


class TestAPI:
    @pytest.mark.parametrize(
        "meta",
        [
            {"zyte_api": {"browserHtml": True}},
            {"zyte_api": {"geolocation": "US"}},
            {"zyte_api": {"geolocation": "US", "echoData": 123}},
            {"zyte_api": {"randomParameter": None}},
        ],
    )
    @pytest.mark.asyncio
    async def test_base_request(self, meta: dict):
        with MockServer() as server:
            async with make_handler({}, server.urljoin("/")) as handler:
                req = Request(
                    "http://example.com",
                    method="POST",
                    meta={"zyte_api": {"geolocation": "US"}},
                )
                resp = await handler._download_request(req, Spider("test"))  # NOQA

            assert resp.request is req
            assert resp.url == req.url
            assert resp.status == 200
            assert "zyte-api" in resp.flags
            assert resp.body == b"<html></html>"

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
        meta,
        server_path,
        exception_type,
        exception_text,
    ):
        with MockServer() as server:
            async with make_handler({}, server.urljoin(server_path)) as handler:
                req = Request("http://example.com", method="POST", meta=meta)
                with pytest.raises(exception_type):
                    await handler._download_request(req, Spider("test"))  # NOQA
                assert exception_text in caplog.text
