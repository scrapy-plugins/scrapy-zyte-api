from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Spider
import pytest

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@pytest.mark.parametrize(
    ("attempts", "expected_stats"),
    (
        (None, {"example.com": (1, 2)}),
        (1, {"example.com": (1, 1)}),
    ),
)
@deferred_f_from_coro_f
async def test_empty_queue(attempts, expected_stats, mockserver):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_SESSION_QUEUE_WAIT_TIME": 0.001,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    if attempts is not None:
        settings["ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS"] = attempts

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"] * 2

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, expected_stats)
