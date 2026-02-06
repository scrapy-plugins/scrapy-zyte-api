import pytest
from scrapy import Spider
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@pytest.mark.parametrize(
    ("params", "close_reason", "stats"),
    (
        (
            {"browserHtml": True},
            "bad_session_inits",
            {"forbidden.example": {"init/failed": 1}},
        ),
        (
            {"browserHtml": True, "url": "https://example.com"},
            "failed_forbidden_domain",
            {"forbidden.example": {"init/check-passed": 1}},
        ),
    ),
)
@deferred_f_from_coro_f
async def test_url_override(params, close_reason, stats, mockserver):
    """If session params define a URL, that URL is used for session
    initialization. Otherwise, the URL from the request getting the session
    assigned first is used for session initialization."""
    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_PARAMS": params,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://forbidden.example"]

        def parse(self, response):
            pass

        def closed(self, reason):
            self.close_reason = reason

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.spider.close_reason == close_reason
    assert_session_stats(crawler, stats)
