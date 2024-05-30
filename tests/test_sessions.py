import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider

from . import get_crawler

UNSET = object()


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
@ensureDeferred
async def test_enabled(setting, meta, outcome, mockserver):
    settings = {"ZYTE_API_URL": mockserver.urljoin("/")}
    if setting is not UNSET:
        settings["ZYTE_API_SESSION_ENABLED"] = setting
    meta_dict = {}
    if meta is not UNSET:
        meta_dict = {"zyte_api_session_enabled": meta}

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request("https://example.com", meta=meta_dict)

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

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
        assert session_stats == {}
