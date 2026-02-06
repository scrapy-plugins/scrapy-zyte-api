from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached

from scrapy_zyte_api.utils import (
    maybe_deferred_to_future,
)

from . import SESSION_SETTINGS, get_crawler


class DomainChecker:
    def check(self, response: Response, request: Request) -> bool:
        domain = urlparse_cached(request).netloc
        return "fail" not in domain


@deferred_f_from_coro_f
async def test_check_overrides_error(mockserver):
    """Max errors are ignored if a session does not pass its session check."""
    retry_times = 2
    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": retry_times,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions_check_errors.DomainChecker",
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_MAX_ERRORS": 2,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-check-fails.example"]

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
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/init/check-passed": retry_times
        + 2,
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/use/check-failed": retry_times
        + 1,
    }
