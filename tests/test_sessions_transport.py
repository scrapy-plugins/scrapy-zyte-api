from __future__ import annotations

import pytest
from scrapy import Request, Spider
from scrapy.http import HtmlResponse
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler


class _TransportRecordingHandler(ScrapyZyteAPIDownloadHandler):
    records: list[dict] = []

    def _record(self, transport, api_params, request):
        _TransportRecordingHandler.records.append(
            {
                "transport": transport,
                "init": "_is_session_init_request" in request.meta,
                "session_id": (api_params.get("session") or {}).get("id"),
            }
        )

    async def _download_via_proxy_mode(self, api_params, request):
        self._record("proxy", api_params, request)
        return await super()._download_via_proxy_mode(api_params, request)

    async def _download_via_http_api(self, api_params, request):
        self._record("http", api_params, request)
        return await super()._download_via_http_api(api_params, request)

    async def _download_via_fallback(self, request, spider=None):
        if request.meta.get("proxy"):
            _TransportRecordingHandler.records.append(
                {
                    "proxy_fallback": True,
                    "zyte_session_id": (
                        request.headers.get(b"Zyte-Session-ID") or b""
                    ).decode(),
                }
            )
            return HtmlResponse(
                request.url,
                body=b"<html><body>proxy ok</body></html>",
                encoding="utf-8",
                headers={b"Content-Type": b"text/html"},
                request=request,
            )
        return await super()._download_via_fallback(request, spider)


HANDLER_PATH = f"{__name__}._TransportRecordingHandler"


@pytest.fixture(autouse=True)
def _reset_records():
    _TransportRecordingHandler.records = []
    yield
    _TransportRecordingHandler.records = []


async def _crawl(mockserver, extra_settings, meta=None):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_TRANSPARENT_MODE": True,
        "DOWNLOAD_HANDLERS": {"http": HANDLER_PATH, "https": HANDLER_PATH},
        "RETRY_TIMES": 0,
        **extra_settings,
    }
    url = mockserver.urljoin("/")

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            yield Request(url, meta=meta or {})

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())
    return crawler


def _transports(records):
    """Return (init_transport, use_transport) from the recorded requests."""
    init = next(r["transport"] for r in records if r.get("init"))
    use = next(
        r["transport"] for r in records if "transport" in r and not r.get("init")
    )
    return init, use


def _session_stat(crawler, suffix):
    for key, value in crawler.stats.get_stats().items():
        if key.startswith("scrapy-zyte-api/sessions/") and key.endswith(suffix):
            return value
    return None


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (
            {"ZYTE_API_TRANSPORT": "proxy", "ZYTE_API_SESSION_TRANSPORT": "proxy"},
            ("proxy", "proxy"),
        ),
        ({"ZYTE_API_TRANSPORT": "proxy"}, ("http", "proxy")),
        ({"ZYTE_API_SESSION_TRANSPORT": "proxy"}, ("proxy", "http")),
        (
            {"ZYTE_API_TRANSPORT": "http", "ZYTE_API_SESSION_TRANSPORT": "http"},
            ("http", "http"),
        ),
    ],
)
@deferred_f_from_coro_f
async def test_session_transport_combinations(settings, expected, mockserver):
    crawler = await _crawl(mockserver, settings)
    assert _transports(_TransportRecordingHandler.records) == expected
    assert _session_stat(crawler, "/init/check-passed") == 1
    assert _session_stat(crawler, "/use/check-passed") == 1


@deferred_f_from_coro_f
async def test_session_id_crosses_transports(mockserver):
    crawler = await _crawl(
        mockserver,
        {"ZYTE_API_TRANSPORT": "proxy", "ZYTE_API_SESSION_TRANSPORT": "proxy"},
    )
    records = _TransportRecordingHandler.records
    assert _session_stat(crawler, "/init/check-passed") == 1
    assert _session_stat(crawler, "/use/check-passed") == 1
    session_ids = {r["session_id"] for r in records if "session_id" in r}
    assert len(session_ids) == 1
    assert None not in session_ids
    header_ids = {r["zyte_session_id"] for r in records if r.get("proxy_fallback")}
    assert header_ids == session_ids


@deferred_f_from_coro_f
async def test_session_transport_meta_overrides_setting(mockserver):
    crawler = await _crawl(
        mockserver,
        {"ZYTE_API_SESSION_TRANSPORT": "http"},
        meta={"zyte_api_session_transport": "proxy"},
    )
    init, _ = _transports(_TransportRecordingHandler.records)
    assert init == "proxy"
    assert _session_stat(crawler, "/init/check-passed") == 1


@deferred_f_from_coro_f
async def test_session_init_experimental_gating(mockserver, caplog):
    with caplog.at_level("WARNING"):
        crawler = await _crawl(mockserver, {})
    init, _ = _transports(_TransportRecordingHandler.records)
    assert init == "http"
    assert (
        crawler.stats.get_value("scrapy-zyte-api/request/transport/proxy/experimental")
        >= 1
    )
    assert "ZYTE_API_SESSION_TRANSPORT" in caplog.text
    assert _session_stat(crawler, "/init/check-passed") == 1


@deferred_f_from_coro_f
async def test_session_transport_invalid_setting(mockserver, caplog):
    with caplog.at_level("ERROR"):
        crawler = await _crawl(mockserver, {"ZYTE_API_SESSION_TRANSPORT": "bogus"})
    assert _session_stat(crawler, "/init/check-passed") is None
    assert "Invalid request transport 'bogus'" in caplog.text
    assert "ZYTE_API_SESSION_TRANSPORT setting" in caplog.text
