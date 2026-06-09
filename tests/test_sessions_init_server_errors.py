"""Tests for session initialization errors that should not count against
ZYTE_API_SESSION_MAX_BAD_INITS: TOO_MANY_SESSIONS and SESSION_CREATION_ERROR."""

from collections import deque
from typing import Any

import pytest
from scrapy import Spider
from scrapy.utils.defer import deferred_f_from_coro_f
from zyte_api import RequestError

from scrapy_zyte_api.utils import _REQUEST_ERROR_HAS_QUERY, maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


def mock_request_error(*, status, response_content):
    kwargs: dict[str, Any] = {}
    if _REQUEST_ERROR_HAS_QUERY:
        kwargs["query"] = {}
    return RequestError(
        history=None,
        request_info=None,
        response_content=response_content,
        status=status,
        **kwargs,
    )


class InitErrorMiddleware:
    """Raises errors for session init requests a fixed number of times (taken
    from ``crawler.init_errors``), then allows them through."""

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self.errors = deque(getattr(crawler, "init_errors", []))

    async def process_request(self, request, spider=None):
        if not request.meta.get("_is_session_init_request"):
            return
        if self.errors:
            raise self.errors.popleft()


@pytest.mark.parametrize(
    ("error_type", "status", "stat"),
    [
        ("/problem/over-session-limit", 422, "over-limit"),
        ("/problem/session-creation-error", 503, "server-error"),
    ],
)
@deferred_f_from_coro_f
async def test_session_init_server_error(error_type, status, stat, mockserver):
    """When session initialization fails with a server-side error (session limit
    reached or session creation failure), it must not count against
    ZYTE_API_SESSION_MAX_BAD_INITS, so the spider keeps running and the session
    is created on the next attempt."""

    settings = {
        **SESSION_SETTINGS,
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
            "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
            "tests.test_sessions_init_server_errors.InitErrorMiddleware": 675,
        },
        # Would close the spider immediately on the first failed init if the
        # error were (wrongly) counted as a bad init.
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.init_errors = [
        mock_request_error(
            status=status,
            response_content=f'{{"type": "{error_type}"}}'.encode(),
        )
    ]
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {
            "example.com": {
                f"init/{stat}": 1,
                "init/check-passed": 1,
                "use/check-passed": 1,
            }
        },
    )
