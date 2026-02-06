from asyncio import sleep
from collections import deque

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider

from scrapy_zyte_api import SessionConfig, session_config
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler


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

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        f"scrapy-zyte-api/sessions/pools/{pool}/init/check-passed": 1,
        f"scrapy-zyte-api/sessions/pools/{pool}/use/check-passed": 1,
    }


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

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com[0]/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com[0]/use/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/example.com[1]/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com[1]/use/check-passed": 1,
    }
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

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }
    assert crawler.spider.close_reason == "finished"

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_session_config_pool_error(mockserver):
    # NOTE: This error should only happen during the initial process_request
    # call. By the time the code reaches process_response, the cached pool
    # value for that request is reused, so there is no new call to
    # SessionConfig.pool that could fail during process_response only.

    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        def pool(self, request: Request):
            raise Exception

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

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {}
    assert crawler.spider.close_reason == "pool_error"

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("settings", "meta", "expected"),
    (
        ({}, None, 1.0),
        ({"ZYTE_API_SESSION_DELAY": 1.5}, None, 1.5),
        ({}, "example.com", 1),
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

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    expected_full = {}
    for pool, (init_count, use_count) in expected_stats.items():
        expected_full[f"scrapy-zyte-api/sessions/pools/{pool}/init/check-passed"] = (
            init_count
        )
        expected_full[f"scrapy-zyte-api/sessions/pools/{pool}/use/check-passed"] = (
            use_count
        )
    assert session_stats == expected_full

    if "ZYTE_API_SESSION_POOL_SIZES" in settings:
        assert any(
            "ZYTE_API_SESSION_POOL_SIZES is deprecated" in rec.getMessage()
            for rec in caplog.records
        )
