import pytest

pytest.importorskip("scrapy_poet")

from typing import Any, Dict

from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider, signals

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats

from scrapy_poet import DummyResponse
from zyte_common_items import Product


@deferred_f_from_coro_f
async def test_provider(mockserver):
    class Tracker:
        def __init__(self):
            self.query: Dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.query = request.meta["zyte_api"]

    tracker = Tracker()

    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com", callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": (1, 1)})
    assert "product" in tracker.query
