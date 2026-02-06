from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Spider

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler


@deferred_f_from_coro_f
async def test_empty_queue(mockserver):
    """After a pool is full, there might be a situation when the middleware
    tries to assign a session to a request but all sessions of the pool are
    pending creation, delay awaiting or a refresh. In those cases, the assign
    process should wait until a session becomes available in the queue."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        # We send 2 requests in parallel, so only the first one gets a session
        # created on demand, and the other one is forced to wait until that
        # session is initialized.
        start_urls = ["https://example.com/1", "https://example.com/2"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 2,
    }


@deferred_f_from_coro_f
async def test_empty_queue_limit(mockserver):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS": 1,
        "ZYTE_API_SESSION_QUEUE_WAIT_TIME": 0,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com/1", "https://example.com/2"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
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
