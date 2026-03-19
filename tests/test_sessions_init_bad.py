import pytest
from scrapy import Spider
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


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
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
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

    assert_session_stats(
        crawler,
        {
            "example.com": {
                "init/failed": 8 if global_setting is None else global_setting
            },
            "pool.example": {"init/failed": value},
        },
    )
