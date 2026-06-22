"""Tests for request-transport handling in the scrapy-poet provider
(:class:`scrapy_zyte_api.providers.ZyteApiProvider`)."""

from copy import deepcopy

import pytest

pytest.importorskip("scrapy_poet")

from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy_poet import DummyResponse
from scrapy_poet.utils.testing import HtmlResource
from web_poet import BrowserResponse

from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler
from scrapy_zyte_api.providers import ZyteApiProvider

from . import SETTINGS
from .test_providers import ZyteAPISpider, _crawl_single_item

_BROWSER_HTML = "<html><body>Hello<h1>World!</h1></body></html>"


class _CapturingHandler(ScrapyZyteAPIDownloadHandler):
    """Records the transport-related meta of provider-generated requests, and
    serves a canned browser-HTML response for proxy sub-requests so that proxy
    mode can be exercised end to end without a real proxy round-trip."""

    captured: list[dict] = []

    async def _dispatch_request(self, request, spider=None):
        if "_zyte_api_transport_explicit" in request.meta:
            _CapturingHandler.captured.append(
                {
                    "zyte_api_transport": request.meta.get("zyte_api_transport"),
                    "_zyte_api_transport_explicit": request.meta.get(
                        "_zyte_api_transport_explicit"
                    ),
                }
            )
        return await super()._dispatch_request(request, spider)

    async def _download_via_fallback(self, request, spider=None):
        # Proxy sub-requests carry a "proxy" meta key; intercept them so the
        # provider's browserHtml request resolves without a real proxy server.
        if request.meta.get("proxy"):
            return HtmlResponse(
                request.url,
                body=_BROWSER_HTML.encode(),
                encoding="utf-8",
                headers={b"Content-Type": [b"text/html"]},
                request=request,
            )
        return await super()._download_via_fallback(request, spider)


HANDLER_PATH = f"{__name__}._CapturingHandler"


@pytest.fixture(autouse=True)
def _reset_captured():
    _CapturingHandler.captured = []
    yield
    _CapturingHandler.captured = []


def _provider_settings(mockserver, **extra):
    settings = deepcopy(SETTINGS)
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["DOWNLOAD_HANDLERS"] = {
        "http": HANDLER_PATH,
        "https": HANDLER_PATH,
    }
    settings.update(extra)
    return settings


class _ProviderTransportSpider(ZyteAPISpider):
    transport = None  # The zyte_api_provider_transport meta value, if any.

    def get_start_request(self):
        meta = {}
        if self.transport is not None:
            meta["zyte_api_provider_transport"] = self.transport
        return Request(
            self.url,
            callback=self.parse_,  # type: ignore[arg-type]
            meta=meta,
        )

    def parse_(self, response: DummyResponse, browser_response: BrowserResponse):  # type: ignore[override]
        yield {"html": str(browser_response.html)}


@pytest.mark.parametrize(
    ("setting", "meta", "expected_transport", "expected_explicit"),
    [
        # Default.
        (None, None, "auto", False),
        # Setting.
        ("http", None, "http", True),
        ("auto", None, "auto", True),
        ("proxy", None, "proxy", True),
        # Request meta.
        (None, "http", "http", True),
        (None, "proxy", "proxy", True),
        # Request meta overrides the setting.
        ("http", "auto", "auto", True),
    ],
)
@deferred_f_from_coro_f
async def test_provider_transport(
    mockserver, setting, meta, expected_transport, expected_explicit
):
    extra = {} if setting is None else {"ZYTE_API_PROVIDER_TRANSPORT": setting}
    settings = _provider_settings(mockserver, **extra)
    item, *_ = await _crawl_single_item(
        _ProviderTransportSpider,
        HtmlResource,
        settings,
        spider_kwargs={"transport": meta},
    )
    assert _CapturingHandler.captured == [
        {
            "zyte_api_transport": expected_transport,
            "_zyte_api_transport_explicit": expected_explicit,
        }
    ]
    assert item["html"] == _BROWSER_HTML
