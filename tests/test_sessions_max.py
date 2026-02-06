from math import floor
from urllib.parse import urlparse

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Spider

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler

RETRY_TIMES = 2
TEST_CASES = [
    *(
        (
            "https://example.com",
            (
                {
                    **(
                        {}
                        if setting is None
                        else {"ZYTE_API_SESSION_MAX_BAD_INITS": setting}
                    ),
                    "ZYTE_API_SESSION_PARAMS": {
                        "browserHtml": True,
                        "httpResponseBody": True,
                    },
                }
            ),
            {"init/failed": value},
        )
        for setting, value in ((0, 1), (1, 1), (2, 2), (None, 8))
    ),
    *(
        (
            "https://example.com",
            (
                {
                    **(
                        {}
                        if setting is None
                        else {"ZYTE_API_SESSION_MAX_CHECK_FAILURES": setting}
                    ),
                    "RETRY_TIMES": RETRY_TIMES,
                    "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY",
                    "ZYTE_API_SESSION_CHECKER": "tests.test_sessions_check_custom.FalseUseChecker",
                    "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
                    "ZYTE_API_SESSION_POOL_SIZE": 1,
                }
            ),
            {
                "init/check-passed": floor((RETRY_TIMES + 1) / value) + 1,
                "use/check-failed": RETRY_TIMES + 1,
            },
        )
        for setting, value in ((None, 1), (0, 1), (1, 1), (2, 2))
    ),
    *(
        (
            "https://temporary-download-error.example",
            (
                {
                    **(
                        {}
                        if setting is None
                        else {"ZYTE_API_SESSION_MAX_ERRORS": setting}
                    ),
                    "RETRY_TIMES": RETRY_TIMES,
                    "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY",
                    "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
                    "ZYTE_API_SESSION_POOL_SIZE": 1,
                }
            ),
            {
                "init/check-passed": floor((RETRY_TIMES + 1) / value) + 1,
                "use/failed": RETRY_TIMES + 1,
            },
        )
        for setting, value in ((None, 1), (0, 1), (1, 1), (2, 2))
    ),
]


@pytest.mark.parametrize(
    ("start_url", "settings", "expected_stats"),
    TEST_CASES,
)
@deferred_f_from_coro_f
async def test_max(start_url, settings, expected_stats, mockserver):
    settings = {**SESSION_SETTINGS, "ZYTE_API_URL": mockserver.urljoin("/"), **settings}

    class TestSpider(Spider):
        name = "test"
        start_urls = [start_url]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }

    pool = urlparse(start_url).netloc
    expected = {}
    for suffix, val in expected_stats.items():
        expected[f"scrapy-zyte-api/sessions/pools/{pool}/{suffix}"] = val

    assert session_stats == expected
