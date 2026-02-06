import pytest
from scrapy import Request, Spider
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.httpobj import urlparse_cached

from scrapy_zyte_api import (
    SessionConfig,
    session_config,
)
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import get_crawler, UNSET


@pytest.mark.parametrize(
    ("setting", "meta", "outcome"),
    (
        (UNSET, UNSET, False),
        (UNSET, True, True),
        (UNSET, False, False),
        (True, UNSET, True),
        (True, True, True),
        (True, False, False),
        (False, UNSET, False),
        (False, True, True),
        (False, False, False),
    ),
)
@deferred_f_from_coro_f
async def test_enabled(setting, meta, outcome, mockserver):
    settings = {"ZYTE_API_URL": mockserver.urljoin("/")}
    if setting is not UNSET:
        settings["ZYTE_API_SESSION_ENABLED"] = setting
    meta_dict = {}
    if meta is not UNSET:
        meta_dict = {"zyte_api_session_enabled": meta}

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com", meta=meta_dict)

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    if outcome:
        assert session_stats == {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
            "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
        }
    else:
        assert session_stats == {
            "scrapy-zyte-api/sessions/use/disabled": 1,
        }


@deferred_f_from_coro_f
async def test_session_config_enabled(mockserver):
    pytest.importorskip("web_poet")

    @session_config(["enabled.example", "disabled.example"])
    class CustomSessionConfig(SessionConfig):
        def enabled(self, request: Request):
            return "enabled" in urlparse_cached(request).netloc

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://enabled.example", "https://disabled.example"]

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
        "scrapy-zyte-api/sessions/use/disabled": 1,
        "scrapy-zyte-api/sessions/pools/enabled.example/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/enabled.example/use/check-passed": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]
