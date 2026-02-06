from copy import deepcopy
from typing import Any, Dict

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider, signals

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import get_crawler


@pytest.mark.parametrize(
    ("settings", "meta", "meta_key"),
    (
        (
            {},
            {},
            "zyte_api",
        ),
        (
            {},
            {"zyte_api": {}},
            "zyte_api",
        ),
        (
            {},
            {"zyte_api": {"httpResponseBody": True}},
            "zyte_api",
        ),
        (
            {},
            {"zyte_api_automap": True},
            "zyte_api_automap",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {},
            "zyte_api_automap",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {"zyte_api_automap": False},
            "zyte_api",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {"zyte_api_automap": {}},
            "zyte_api_automap",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {"zyte_api_automap": True},
            "zyte_api_automap",
        ),
    ),
)
@deferred_f_from_coro_f
async def test_assign_meta_key(settings, meta, meta_key, mockserver):
    """Session ID is set in the zyte_api_provider meta key always, and in
    either zyte_api or zyte_api_automap depending on some settings and meta
    keys."""

    class Tracker:
        def __init__(self):
            self.meta: Dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.meta = deepcopy(request.meta)

    tracker = Tracker()

    settings = {
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        **settings,
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request(
                "https://example.com",
                meta=meta,
            )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }

    assert (
        tracker.meta["zyte_api_provider"]["session"]
        == tracker.meta[meta_key]["session"]
    )
    other_meta_key = "zyte_api" if meta_key != "zyte_api" else "zyte_api_automap"
    assert tracker.meta.get(other_meta_key, False) is False
