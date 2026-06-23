"""Integration tests verifying session behavior across redirects, meta-refreshes,
and Scrapy-level retries when using the add-on."""

from scrapy import Request, Spider, signals
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api import get_request_session_id, is_session_init_request
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler


class _SessionTracker:
    def __init__(self):
        self.sessions = []

    def track(self, request: Request, spider: Spider):
        if is_session_init_request(request):
            return
        session_id = get_request_session_id(request)
        if session_id:
            self.sessions.append(session_id)


@deferred_f_from_coro_f
async def test_session_preserved_on_redirect(mockserver):
    """The redirect request produced by Scrapy's RedirectMiddleware reuses
    the same session as the original request, preserving IP consistency."""

    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-redirect.example/"]

        def parse(self, response):
            pass

    tracker = _SessionTracker()
    crawler = await get_crawler(
        settings, spider_cls=TestSpider, setup_engine=False, use_addon=True
    )
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    # original request + redirect request, both using the same session
    assert len(tracker.sessions) == 2
    assert tracker.sessions[0] == tracker.sessions[1]


@deferred_f_from_coro_f
async def test_session_preserved_on_meta_refresh(mockserver):
    """The request produced by Scrapy's MetaRefreshMiddleware reuses the same
    session as the original request, preserving IP consistency."""

    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-meta-refresh.example/"]

        def parse(self, response):
            pass

    tracker = _SessionTracker()
    crawler = await get_crawler(
        settings, spider_cls=TestSpider, setup_engine=False, use_addon=True
    )
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    # original request + meta-refresh request, both using the same session
    assert len(tracker.sessions) == 2
    assert tracker.sessions[0] == tracker.sessions[1]


@deferred_f_from_coro_f
async def test_session_rotated_on_retry(mockserver):
    """When Scrapy's RetryMiddleware retries a request, the retry uses a
    different session than the original, allowing session rotation."""

    settings = {
        **SESSION_SETTINGS,
        "RETRY_HTTP_CODES": [500],
        "RETRY_TIMES": 1,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 2,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-retry.example/"]

        def parse(self, response):
            pass

    tracker = _SessionTracker()
    crawler = await get_crawler(
        settings, spider_cls=TestSpider, setup_engine=False, use_addon=True
    )
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    # original request + retry request, each using a different session
    assert len(tracker.sessions) == 2
    assert tracker.sessions[0] != tracker.sessions[1]
