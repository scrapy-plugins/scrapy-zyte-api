from collections import deque
from copy import copy
from typing import Any, Dict, Union
from unittest.mock import patch

import pytest
from aiohttp.client_exceptions import ServerConnectionError
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider
from scrapy.http import Response
from zyte_api import RequestError

from scrapy_zyte_api import (
    SESSION_AGGRESSIVE_RETRY_POLICY,
    SESSION_DEFAULT_RETRY_POLICY,
)
from scrapy_zyte_api.utils import (
    _REQUEST_ERROR_HAS_QUERY,
    maybe_deferred_to_future,
)

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


def mock_request_error(*, status=200, response_content=None):
    kwargs: Dict[str, Any] = {}
    if _REQUEST_ERROR_HAS_QUERY:
        kwargs["query"] = {}
    return RequestError(
        history=None,
        request_info=None,
        response_content=response_content,
        status=status,
        **kwargs,
    )


# Number of times to test request errors that must be retried forever.
FOREVER_TIMES = 100


class fast_forward:
    def __init__(self, time):
        self.time = time


@pytest.mark.parametrize(
    ("retrying", "outcomes", "exhausted"),
    (
        *(
            (retry_policy, outcomes, exhausted)
            for retry_policy in (
                SESSION_DEFAULT_RETRY_POLICY,
                SESSION_AGGRESSIVE_RETRY_POLICY,
            )
            for status in (520, 521)
            for outcomes, exhausted in (
                (
                    (mock_request_error(status=status),),
                    True,
                ),
                (
                    (mock_request_error(status=429),),
                    False,
                ),
                (
                    (
                        mock_request_error(status=429),
                        mock_request_error(status=status),
                    ),
                    True,
                ),
            )
        ),
    ),
)
@deferred_f_from_coro_f
@patch("time.monotonic")
async def test_retry_stop(monotonic_mock, retrying, outcomes, exhausted):
    monotonic_mock.return_value = 0
    last_outcome = outcomes[-1]
    outcomes = deque(outcomes)

    def wait(retry_state):
        return 0.0

    retrying = copy(retrying)
    retrying.wait = wait

    async def run():
        while True:
            try:
                outcome = outcomes.popleft()
            except IndexError:
                return
            else:
                if isinstance(outcome, fast_forward):
                    monotonic_mock.return_value += outcome.time
                    continue
                raise outcome

    run = retrying.wraps(run)
    try:
        await run()
    except Exception as outcome:
        assert exhausted
        assert outcome is last_outcome
    else:
        assert not exhausted


class SessionIDRemovingDownloaderMiddleware:
    def process_exception(
        self, request: Request, exception: Exception, spider: Spider | None = None
    ) -> Union[Request, None]:
        if not isinstance(exception, RequestError) or request.meta.get(
            "_is_session_init_request", False
        ):
            return None

        del request.meta["zyte_api_automap"]["session"]
        del request.meta["zyte_api_provider"]["session"]
        return None


class SessionIDRemovingResponseMiddleware:
    def process_response(
        self, request: Request, response: Response, spider: Spider | None = None
    ) -> Response:
        if request.meta.get("_is_session_init_request", False):
            return response
        for meta_key in ("zyte_api_automap", "zyte_api_provider"):
            if meta_key in request.meta and isinstance(request.meta[meta_key], dict):
                request.meta[meta_key].pop("session", None)
        return response


@deferred_f_from_coro_f
async def test_missing_session_id(mockserver, caplog):
    """If a session ID is missing from a request that should have had it
    assigned, a warning is logged about it."""

    settings = {
        **SESSION_SETTINGS,
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
            "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
            "tests.test_sessions_errors.SessionIDRemovingDownloaderMiddleware": 675,
        },
        "RETRY_TIMES": 0,
        "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY",
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_TRANSPARENT_MODE": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://temporary-download-error.example"]

        def parse(self, response):
            pass

    caplog.clear()
    caplog.set_level("WARNING")
    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {"temporary-download-error.example": {"init/check-passed": 1, "use/failed": 1}},
    )
    assert "had no session ID assigned, unexpectedly" in caplog.text


class ExceptionRaisingDownloaderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self.crawler = crawler

    async def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> None:
        if request.meta.get("_is_session_init_request", False):
            return
        raise self.crawler.exception


@pytest.mark.parametrize(
    ("exception", "stat", "reason"),
    (
        (
            mock_request_error(
                status=422, response_content=b'{"type": "/problem/session-expired"}'
            ),
            "expired",
            "session_expired",
        ),
        (
            mock_request_error(status=520),
            "failed",
            "download_error",
        ),
        (
            mock_request_error(status=521),
            "failed",
            "download_error",
        ),
        (
            mock_request_error(status=500),
            None,
            None,
        ),
        (
            ServerConnectionError(),
            None,
            None,
        ),
        (
            RuntimeError(),
            None,
            None,
        ),
    ),
)
@deferred_f_from_coro_f
async def test_exceptions(exception, stat, reason, mockserver, caplog):
    settings = {
        **SESSION_SETTINGS,
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
            "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
            "tests.test_sessions_errors.ExceptionRaisingDownloaderMiddleware": 675,
        },
        "RETRY_TIMES": 0,
        "ZYTE_API_TRANSPARENT_MODE": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def parse(self, response):
            pass

    caplog.clear()
    caplog.set_level("ERROR")
    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.exception = exception
    await maybe_deferred_to_future(crawler.crawl())

    if stat is not None:
        assert_session_stats(
            crawler,
            {"example.com": {"init/check-passed": 2, f"use/{stat}": 1}},
        )
    else:
        assert_session_stats(crawler, {"example.com": {"init/check-passed": 1}})
    if reason is not None:
        assert reason in caplog.text


@deferred_f_from_coro_f
async def test_missing_session_id_on_response(mockserver, caplog):
    settings = {
        **SESSION_SETTINGS,
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
            "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
            "tests.test_sessions_errors.SessionIDRemovingResponseMiddleware": 675,
        },
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions_check_errors.DomainChecker",
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-check-fails.example"]

        def parse(self, response):
            pass

    caplog.clear()
    caplog.set_level("WARNING")
    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert "had no session ID assigned, unexpectedly" in caplog.text
