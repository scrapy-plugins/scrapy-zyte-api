from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider, signals

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler


@deferred_f_from_coro_f
async def test_session_refresh(mockserver):
    """If a response does not pass a session validity check, the session is
    discarded, and the request is retried with a different session."""

    class Tracker:
        def __init__(self):
            self.sessions = []

        def track_session(self, request: Request, spider: Spider):
            self.sessions.append(request.meta["zyte_api"]["session"]["id"])

    tracker = Tracker()

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions_check_errors.DomainChecker",
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-check-fails.example"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(
        tracker.track_session, signal=signals.request_reached_downloader
    )
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/init/check-passed": 3,
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/use/check-failed": 2,
    }
    assert len(tracker.sessions) == 5
    assert tracker.sessions[0] == tracker.sessions[1]
    assert tracker.sessions[0] != tracker.sessions[2]
    assert tracker.sessions[2] == tracker.sessions[3]
    assert tracker.sessions[0] != tracker.sessions[4]
    assert tracker.sessions[2] != tracker.sessions[4]


@deferred_f_from_coro_f
async def test_session_refresh_concurrent(mockserver):
    """When more than 1 request is using the same session concurrently, it can
    happen that more than 1 response triggers a session refresh. In those
    cases, the same session should be refreshed only once, not once per
    response triggering a refresh."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_MAX_ERRORS": 1,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com/"]

        def parse(self, response):
            for n in range(2):
                yield Request(f"https://example.com/{n}?temporary-download-error")

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/failed": 2,
    }
