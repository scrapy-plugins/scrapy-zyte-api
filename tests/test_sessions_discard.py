import logging

import pytest
from scrapy import Request, Spider, signals
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.http.response import Response

from scrapy_zyte_api import (
    ScrapyZyteAPISessionDownloaderMiddleware,
    SessionConfig,
    session_config,
    session_config_registry,
)
from scrapy_zyte_api._session import PoolError
from scrapy_zyte_api.utils import _GET_COMPONENT_SUPPORT, maybe_deferred_to_future

from . import SESSION_SETTINGS, deferred_f_from_coro_f, get_crawler
from .helpers import assert_session_stats

pytestmark = pytest.mark.skipif(
    not _GET_COMPONENT_SUPPORT,
    reason="Discarding sessions from user code requires Scrapy 2.12 or higher",
)

SETTINGS = {
    **SESSION_SETTINGS,
    "RETRY_TIMES": 1,
    "ZYTE_API_SESSION_POOL_SIZE": 1,
    # With a single session per pool, discarding a session empties the session
    # rotation queue, so retries must wait for the replacement session.
    "ZYTE_API_SESSION_QUEUE_WAIT_TIME": 0.1,
}


class SessionTracker:
    """Keeps track of the session ID used by every Zyte API request."""

    def __init__(self):
        self.sessions: list[str] = []

    def track(self, request: Request, spider: Spider):
        self.sessions.append(request.meta["zyte_api"]["session"]["id"])


async def crawl(mockserver, spider_cls, settings=None):
    tracker = SessionTracker()
    crawler = await get_crawler(
        {
            **SETTINGS,
            "ZYTE_API_URL": mockserver.urljoin("/"),
            **(settings or {}),
        },
        spider_cls=spider_cls,
        setup_engine=False,
    )
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())
    return crawler, tracker


def get_session_middleware(spider):
    return spider.crawler.get_downloader_middleware(
        ScrapyZyteAPISessionDownloaderMiddleware
    )


@deferred_f_from_coro_f
async def test_response(mockserver):
    """discard_session() can take a response, and the request can then be
    retried with a different session."""

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            if "retry_times" in response.request.meta:
                return
            get_session_middleware(self).discard_session(response)
            yield get_retry_request(response.request, spider=self, reason="test")

    crawler, tracker = await crawl(mockserver, TestSpider)

    assert_session_stats(
        crawler,
        {
            "example.com": {
                "init/check-passed": 2,
                "use/check-passed": 2,
                "use/discarded": 1,
            }
        },
    )
    # 1st session initialization, 1st request, 2nd session initialization,
    # retry.
    assert len(tracker.sessions) == 4
    assert tracker.sessions[0] == tracker.sessions[1]
    assert tracker.sessions[2] == tracker.sessions[3]
    assert tracker.sessions[0] != tracker.sessions[3]


@deferred_f_from_coro_f
async def test_request(mockserver):
    """discard_session() can also take a request."""

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            get_session_middleware(self).discard_session(response.request)

    crawler, _ = await crawl(mockserver, TestSpider)

    assert_session_stats(
        crawler,
        {
            "example.com": {
                "init/check-passed": 2,
                "use/check-passed": 1,
                "use/discarded": 1,
            }
        },
    )


@deferred_f_from_coro_f
async def test_response_without_request(mockserver):
    """discard_session() raises ValueError for a response without a request."""
    exceptions = []

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            middleware = get_session_middleware(self)
            try:
                middleware.discard_session(Response("https://example.com"))
            except ValueError as exception:
                exceptions.append(exception)

    crawler, _ = await crawl(mockserver, TestSpider)

    assert len(exceptions) == 1
    assert "which has no request assigned" in str(exceptions[0])
    assert_session_stats(crawler, {"example.com": (1, 1)})


@deferred_f_from_coro_f
async def test_session_management_disabled(mockserver, caplog):
    """Discarding the session of a request that does not use session management
    logs a warning and does nothing."""

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request(
                "https://example.com", meta={"zyte_api_session_enabled": False}
            )

        def parse(self, response):
            get_session_middleware(self).discard_session(response)

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        crawler, _ = await crawl(mockserver, TestSpider)

    assert "which does not use session management" in caplog.text
    assert_session_stats(crawler, {"/use/disabled": 1})


@deferred_f_from_coro_f
async def test_request_without_session(mockserver, caplog):
    """Discarding the session of a request that has no session assigned logs a
    warning and does nothing."""

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            get_session_middleware(self).discard_session(Request("https://example.com"))

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        crawler, _ = await crawl(mockserver, TestSpider)

    assert "which has no session assigned" in caplog.text
    assert_session_stats(crawler, {"example.com": (1, 1)})


@deferred_f_from_coro_f
async def test_pool_error(mockserver):
    """If determining the session pool of the target request fails, the spider
    is closed with the pool_error reason, and the exception reaches the
    caller."""
    pytest.importorskip("web_poet")

    @session_config(["pool-error.example"])
    class CustomSessionConfig(SessionConfig):
        def pool(self, request: Request):
            raise Exception

    exceptions = []

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            try:
                get_session_middleware(self).discard_session(
                    Request("https://pool-error.example")
                )
            except PoolError as exception:
                exceptions.append(exception)

        def closed(self, reason):
            self.close_reason = reason

    try:
        crawler, _ = await crawl(mockserver, TestSpider)
    finally:
        session_config_registry.__init__()  # type: ignore[misc]

    assert len(exceptions) == 1
    assert crawler.spider.close_reason == "pool_error"
