from copy import deepcopy
from typing import Any

import pytest
from scrapy import Request, Spider, signals
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@pytest.mark.parametrize(
    ("settings", "meta", "meta_key"),
    [
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
            # The zyte_api_transport metadata key opts an otherwise-bare request
            # into automatic request parameter mapping, so the session ID goes
            # into zyte_api_automap rather than zyte_api.
            {},
            {"zyte_api_transport": "http"},
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
    ],
)
@deferred_f_from_coro_f
async def test_assign_meta_key(settings, meta, meta_key, mockserver):
    """Session ID is set in the zyte_api_provider meta key always, and in
    either zyte_api or zyte_api_automap depending on some settings and meta
    keys."""

    class Tracker:
        def __init__(self):
            self.meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.meta = deepcopy(request.meta)

    tracker = Tracker()

    settings = {
        **SESSION_SETTINGS,
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

    assert_session_stats(crawler, {"example.com": (1, 1)})

    assert (
        tracker.meta["zyte_api_provider"]["session"]
        == tracker.meta[meta_key]["session"]
    )
    other_meta_key = "zyte_api" if meta_key != "zyte_api" else "zyte_api_automap"
    assert tracker.meta.get(other_meta_key, False) is False


@deferred_f_from_coro_f
async def test_assign_session_extra_keys(mockserver):
    """assign() sets the managed session ID while preserving any other session
    keys the request already defines, overriding an explicitly-set ID."""

    class Tracker:
        def __init__(self):
            self.meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.meta = deepcopy(request.meta)

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
            yield Request(
                "https://example.com",
                meta={
                    "zyte_api": {
                        "browserHtml": True,
                        "session": {"extraKey": "value", "id": "user-set"},
                    }
                },
            )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": (1, 1)})

    session = tracker.meta["zyte_api"]["session"]
    # The extra key is preserved, and the managed ID overrides the user-set one.
    assert session["extraKey"] == "value"
    assert session["id"] != "user-set"
    assert session["id"] == tracker.meta["zyte_api_provider"]["session"]["id"]
