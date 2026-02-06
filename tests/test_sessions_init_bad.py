import pytest
from scrapy import Spider
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import get_crawler


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        (0, 1),
        (1, 1),
        (2, 2),
        (None, 8),
    ),
)
@deferred_f_from_coro_f
async def test_max_bad_inits(setting, value, mockserver):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_PARAMS": {"browserHtml": True, "httpResponseBody": True},
    }
    if setting is not None:
        settings["ZYTE_API_SESSION_MAX_BAD_INITS"] = setting

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

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
        "scrapy-zyte-api/sessions/pools/example.com/init/failed": value,
    }


@pytest.mark.parametrize(
    ("global_setting", "pool_setting", "value"),
    (
        (None, 0, 1),
        (None, 1, 1),
        (None, 2, 2),
        (3, None, 3),
    ),
)
@deferred_f_from_coro_f
async def test_max_bad_inits_per_pool(global_setting, pool_setting, value, mockserver):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_PARAMS": {"browserHtml": True, "httpResponseBody": True},
    }
    if global_setting is not None:
        settings["ZYTE_API_SESSION_MAX_BAD_INITS"] = global_setting
    if pool_setting is not None:
        settings["ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL"] = {
            "pool.example": pool_setting
        }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com", "https://pool.example"]

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
        "scrapy-zyte-api/sessions/pools/example.com/init/failed": (
            8 if global_setting is None else global_setting
        ),
        "scrapy-zyte-api/sessions/pools/pool.example/init/failed": value,
    }
