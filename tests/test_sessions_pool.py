from collections import deque

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider

from scrapy_zyte_api import SessionConfig, session_config
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import get_crawler


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
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
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
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
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


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        (1, 1),
        (2, 2),
        (None, 8),
    ),
)
@deferred_f_from_coro_f
async def test_pool_size(setting, value, mockserver):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
    }
    if setting is not None:
        settings["ZYTE_API_SESSION_POOL_SIZE"] = setting

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"] * (value + 1)

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
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": value,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": value + 1,
    }


@pytest.mark.parametrize(
    ("global_setting", "pool_setting", "value"),
    (
        (None, 1, 1),
        (None, 2, 2),
        (3, None, 3),
    ),
)
@deferred_f_from_coro_f
async def test_pool_sizes(global_setting, pool_setting, value, mockserver):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
    }
    if global_setting is not None:
        settings["ZYTE_API_SESSION_POOL_SIZE"] = global_setting
    if pool_setting is not None:
        settings["ZYTE_API_SESSION_POOL_SIZES"] = {"pool.example": pool_setting}

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com", "https://pool.example"] * (value + 1)

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
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": (
            value if pool_setting is None else min(value + 1, 8)
        ),
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": value + 1,
        "scrapy-zyte-api/sessions/pools/pool.example/init/check-passed": value,
        "scrapy-zyte-api/sessions/pools/pool.example/use/check-passed": value + 1,
    }


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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
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
