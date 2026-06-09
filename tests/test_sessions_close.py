"""Tests for session manager behavior when the spider close signal fires."""

from asyncio import create_task, sleep

import pytest
from scrapy import Request, Spider, signals
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api import ScrapyZyteAPISessionDownloaderMiddleware
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler, get_downloader_middleware


@deferred_f_from_coro_f
async def test_closing_flag_set_on_spider_closed(mockserver):
    """The _closing flag is set when spider_closed fires."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    sessions = mw._sessions

    assert sessions._closing is False
    crawler.signals.send_catch_log(
        signals.spider_closed, spider=crawler.spider, reason="finished"
    )
    assert sessions._closing is True


@deferred_f_from_coro_f
async def test_init_tasks_cancelled_on_spider_closed(mockserver):
    """Pending session init tasks are cancelled when spider_closed fires."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    sessions = mw._sessions

    # Create a dummy long-running task and register it as an init task.
    task = create_task(sleep(9999))
    sessions._init_tasks.add(task)

    crawler.signals.send_catch_log(
        signals.spider_closed, spider=crawler.spider, reason="finished"
    )
    # Give the event loop a chance to process the cancellation.
    await sleep(0)

    assert task.cancelled()


@deferred_f_from_coro_f
async def test_no_new_refresh_tasks_after_closing(mockserver):
    """_start_session_refresh does not create new tasks when closing."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    sessions = mw._sessions

    crawler.signals.send_catch_log(
        signals.spider_closed, spider=crawler.spider, reason="finished"
    )
    assert sessions._closing is True

    request = Request("https://example.com", meta={"zyte_api": {}})
    # Populate pools so _start_session_refresh can remove the session.
    sessions._pools["example.com"].add("some-session-id")

    sessions._start_session_refresh("some-session-id", request, "example.com")

    # No new background task should have been started.
    assert len(sessions._init_tasks) == 0


@deferred_f_from_coro_f
async def test_create_session_raises_ignore_request_when_closing(mockserver):
    """_create_session raises IgnoreRequest immediately when _closing is True."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    sessions = mw._sessions
    sessions._closing = True

    request = Request(
        "https://example.com",
        meta={"zyte_api": {"browserHtml": True}},
    )

    with pytest.raises(IgnoreRequest):
        await sessions._create_session(request, "example.com")


@deferred_f_from_coro_f
async def test_next_from_queue_raises_ignore_request_when_closing(mockserver):
    """_next_from_queue raises IgnoreRequest when closing and queue is empty."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    sessions = mw._sessions
    sessions._closing = True

    request = Request("https://example.com", meta={"zyte_api": {}})
    # Ensure queue and pool are empty for the target pool.
    sessions._pools["example.com"].clear()
    sessions._queues["example.com"].clear()

    with pytest.raises(IgnoreRequest):
        await sessions._next_from_queue(request, "example.com")


@deferred_f_from_coro_f
async def test_closing_flag_set_after_crawl(mockserver):
    """After a crawl finishes, _closing is True and no init tasks hang."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_PARAMS": {"browserHtml": True},
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    sessions = mw._sessions

    assert sessions._closing is True
    assert len(sessions._init_tasks) == 0


class _CloseSpiderChecker:
    """Checker that always raises CloseSpider on session use."""

    def check(self, response, request):
        raise CloseSpider("checker_close")


@deferred_f_from_coro_f
async def test_close_spider_from_checker_use(mockserver):
    """CloseSpider raised by a session checker propagates as the close reason."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions_close._CloseSpiderChecker",
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_PARAMS": {"browserHtml": True},
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "RETRY_TIMES": 0,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

        def closed(self, reason):
            self.close_reason = reason

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    # After close, no background init tasks should be running.
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    assert mw._sessions._closing is True
    assert len(mw._sessions._init_tasks) == 0
    assert crawler.spider.close_reason == "checker_close"
