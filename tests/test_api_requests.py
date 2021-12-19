import pytest
from scrapy import Request, Spider
from twisted.internet.asyncioreactor import install as install_asyncio_reactor

from tests import make_handler
from tests.mockserver import MockServer

install_asyncio_reactor()


class TestAPI:
    @pytest.mark.asyncio
    async def test_post_request(self):
        custom_settings = {}
        with MockServer() as server:
            async with make_handler(custom_settings, server.urljoin("/")) as handler:
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
