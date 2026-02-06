from asyncio import sleep
from collections import deque

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider

from scrapy_zyte_api import SessionConfig, session_config
from scrapy_zyte_api._session import (
    ScrapyZyteAPISessionDownloaderMiddleware,
    session_config_registry,
)
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler, get_downloader_middleware
from .helpers import assert_session_stats


@pytest.mark.parametrize(
    ("meta", "pool"),
    (
        ({}, "example.com"),
        ({"zyte_api_session_location": {"postalCode": "10001"}}, "example.com@10001"),
        (
            {"zyte_api_session_location": {"postalCode": "10001", "foo": "bar"}},
            "example.com@10001",
        ),
        (
            {
                "zyte_api_session_location": {
                    "addressCountry": "US",
                    "addressRegion": "TX",
                }
            },
            "example.com@US,TX",
        ),
        (
            {
                "zyte_api_session_location": {
                    "addressCountry": "ES",
                    "addressRegion": "Pontevedra",
                    "streetAddress": "Rúa do Príncipe, 123",
                    "postalCode": "12345",
                }
            },
            "example.com@ES,Pontevedra,12345,Rúa do Príncipe, 123",
        ),
        (
            {
                "zyte_api_session_params": {"foo": "bar"},
                "zyte_api_session_location": {"postalCode": "10001"},
            },
            "example.com[0]",
        ),
        (
            {
                "zyte_api_session_pool": "foo",
                "zyte_api_session_params": {"foo": "bar"},
                "zyte_api_session_location": {"postalCode": "10001"},
            },
            "foo",
        ),
    ),
)
@deferred_f_from_coro_f
async def test_pool(meta, pool, mockserver):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com", meta=meta)

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler, {pool: {"init/check-passed": 1, "use/check-passed": 1}}
    )


@deferred_f_from_coro_f
async def test_pool_params(mockserver, caplog):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request(
                "https://example.com/a",
                meta={"zyte_api_session_params": {"foo": "bar"}},
            )
            yield Request(
                "https://example.com/b",
                meta={"zyte_api_session_params": {"foo": "bar"}},
            )
            yield Request(
                "https://example.com/c",
                meta={"zyte_api_session_params": {"foo": "baz"}},
            )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    caplog.clear()
    caplog.set_level("INFO")
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {
            "example.com[0]": {"init/check-passed": 1, "use/check-passed": 2},
            "example.com[1]": {"init/check-passed": 1, "use/check-passed": 1},
        },
    )
    expected_logs = {
        (
            "INFO",
            "Session pool example.com[0] uses these session initialization parameters: {'foo': 'bar'}",
        ): 0,
        (
            "INFO",
            "Session pool example.com[1] uses these session initialization parameters: {'foo': 'baz'}",
        ): 0,
    }
    for record in caplog.records:
        entry = (record.levelname, record.msg)
        if entry in expected_logs:
            expected_logs[entry] += 1
    assert all(v == 1 for v in expected_logs.values())


@deferred_f_from_coro_f
async def test_session_config_pool_caching(mockserver):
    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        def __init__(self, crawler):
            super().__init__(crawler)
            self.pools = deque(("example.com",))

        def pool(self, request: Request):
            # The following code would fail on the second call, which never
            # happens due to pool caching.
            return self.pools.popleft()

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
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

    assert_session_stats(
        crawler, {"example.com": {"init/check-passed": 1, "use/check-passed": 1}}
    )
    assert crawler.spider.close_reason == "finished"

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@pytest.mark.parametrize("outcome", [Exception, 123, {}])
@deferred_f_from_coro_f
async def test_pool_error(mockserver, outcome):
    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        def pool(self, request: Request):
            if isinstance(outcome, type) and issubclass(outcome, Exception):
                raise outcome
            return outcome

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
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

    assert_session_stats(crawler, {})
    assert crawler.spider.close_reason == "pool_error"

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_mw_get_pool(mockserver):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    request = Request("https://example.com", meta={"zyte_api_session_pool": "foo"})
    assert mw.get_pool(request) == "foo"

    # get_pool() is None is plugin-managed sessions are disabled.
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    crawler = await get_crawler(settings)
    mw = get_downloader_middleware(crawler, ScrapyZyteAPISessionDownloaderMiddleware)
    assert mw.get_pool(request) is None


@pytest.mark.parametrize(
    ("settings", "meta", "expected"),
    (
        ({}, None, 0.0),
        ({"DOWNLOAD_DELAY": 1.0}, None, 1.0),
        ({"ZYTE_API_SESSION_DELAY": 1.5}, None, 1.5),
        ({}, "example.com", 0.0),
        ({}, {"id": "example.com", "delay": 1.5}, 1.5),
        (
            {"ZYTE_API_SESSION_POOLS": {"example.com": {"delay": 0.5}}},
            {"id": "example.com", "delay": 1.5},
            0.5,
        ),
    ),
)
@deferred_f_from_coro_f
async def test_delay(settings, meta, expected, mockserver, monkeypatch):
    queue_wait_time = expected + 0.1
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_SESSION_QUEUE_WAIT_TIME": queue_wait_time,
        "ZYTE_API_SESSION_RANDOMIZE_DELAY": False,
        **settings,
    }

    sleep_calls = []

    async def fake_sleep(delay):
        if delay != pytest.approx(queue_wait_time):
            sleep_calls.append(delay)
        await sleep(0)

    monkeypatch.setattr("scrapy_zyte_api._session.sleep", fake_sleep)

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            for url in self.start_urls:
                if meta is None:
                    yield Request(url)
                else:
                    yield Request(url, meta={"zyte_api_session_pool": meta})

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(expected)


@deferred_f_from_coro_f
async def test_delay_reuse(mockserver, monkeypatch):
    """Ensure that non-random delays during session reuse (as opposed to
    creation) work as expected."""
    expected = 0.0  # No delay by default
    queue_wait_time = expected + 0.1
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_SESSION_QUEUE_WAIT_TIME": queue_wait_time,
        "ZYTE_API_SESSION_RANDOMIZE_DELAY": False,
    }

    sleep_calls = []

    async def fake_sleep(delay):
        if delay != pytest.approx(queue_wait_time):
            sleep_calls.append(delay)
        await sleep(0)

    monkeypatch.setattr("scrapy_zyte_api._session.sleep", fake_sleep)

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"] * 2

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("settings", "start_requests"),
    (
        ({"ZYTE_API_SESSION_RANDOMIZE_DELAY": True}, ["https://example.com"] * 2),
        (
            {"ZYTE_API_SESSION_POOLS": {"example.com": {"randomize_delay": True}}},
            ["https://example.com"] * 2,
        ),
        (
            {},
            [
                Request(
                    "https://example.com",
                    meta={
                        "zyte_api_session_pool": {
                            "id": "example.com",
                            "randomize_delay": True,
                        }
                    },
                )
                for _ in range(2)
            ],
        ),
    ),
)
@deferred_f_from_coro_f
async def test_delay_random(settings, start_requests, mockserver, monkeypatch):
    base_delay = 1.0
    queue_wait_time = base_delay * 2
    settings = {
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_SESSION_DELAY": base_delay,
        "ZYTE_API_SESSION_QUEUE_WAIT_TIME": queue_wait_time,
        **settings,
    }

    sleep_calls = []

    async def fake_sleep(delay):
        if delay != pytest.approx(queue_wait_time):
            sleep_calls.append(delay)
        await sleep(0)

    monkeypatch.setattr("scrapy_zyte_api._session.sleep", fake_sleep)

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            for item in start_requests:
                if isinstance(item, str):
                    yield Request(item, dont_filter=True)
                else:
                    yield item.replace(dont_filter=True)

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert len(sleep_calls) == 2
    assert any(call != pytest.approx(base_delay) for call in sleep_calls)


@pytest.mark.parametrize(
    ("settings", "start_requests", "expected_stats"),
    (
        (
            {"ZYTE_API_SESSION_POOL_SIZE": 1},
            ["https://example.com"] * (1 + 1),
            {"example.com": (1, 1 + 1)},
        ),
        (
            {},
            ["https://example.com"] * (8 + 1),
            {"example.com": (8, 8 + 1)},
        ),
        (
            {"ZYTE_API_SESSION_POOL_SIZES": {"pool.example": 1}},
            (["https://example.com", "https://pool.example"] * (1 + 1)),
            {"example.com": (1 + 1, 1 + 1), "pool.example": (1, 1 + 1)},
        ),
        (
            {
                "ZYTE_API_SESSION_POOL_SIZES": {"example.com": 2},
                "ZYTE_API_SESSION_POOLS": {"example.com": {}},
            },
            ["https://example.com"] * (2 + 1),
            {"example.com": (2, 2 + 1)},
        ),
        (
            {
                "ZYTE_API_SESSION_POOL_SIZES": {"example.com": 2},
                "ZYTE_API_SESSION_POOLS": {"example.com": {"size": 1}},
            },
            ["https://example.com"] * (1 + 1),
            {"example.com": (1, 1 + 1)},
        ),
        (
            {"ZYTE_API_SESSION_POOL_SIZE": 1},
            [
                Request(
                    "https://example.com",
                    meta={"zyte_api_session_pool": {"id": "example.com", "size": 2}},
                )
                for _ in range(2 + 1)
            ],
            {"example.com": (2, 2 + 1)},
        ),
        (
            {"ZYTE_API_SESSION_POOLS": {"example.com": {"size": 1}}},
            [
                Request(
                    "https://example.com",
                    meta={"zyte_api_session_pool": {"id": "example.com", "size": 2}},
                )
                for _ in range(2 + 1)
            ],
            {"example.com": (1, 2 + 1)},
        ),
    ),
)
@deferred_f_from_coro_f
async def test_size(settings, start_requests, expected_stats, mockserver, caplog):
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        **settings,
    }

    caplog.clear()
    caplog.set_level("WARNING")

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            for item in start_requests:
                if isinstance(item, str):
                    yield Request(item, dont_filter=True)
                else:
                    yield item.replace(dont_filter=True)

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, expected_stats)

    if "ZYTE_API_SESSION_POOL_SIZES" in settings:
        assert any(
            "ZYTE_API_SESSION_POOL_SIZES is deprecated" in rec.getMessage()
            for rec in caplog.records
        )
