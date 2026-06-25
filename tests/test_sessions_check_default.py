import pytest
from scrapy import Request, Spider
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.test import get_crawler as scrapy_get_crawler

from scrapy_zyte_api import SessionConfig
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@pytest.mark.parametrize(
    ("postal_code", "url", "close_reason", "stats"),
    [
        (
            None,
            "https://postal-code-10001-soft.example",
            "finished",
            {"postal-code-10001-soft.example": (1, 1)},
        ),
        (
            "10001",
            "https://postal-code-10001-soft.example",
            "finished",
            {"postal-code-10001-soft.example": (1, 1)},
        ),
        (
            "10002",
            "https://postal-code-10001-soft.example",
            "bad_session_inits",
            {"postal-code-10001-soft.example": {"init/check-failed": 1}},
        ),
        (
            "10001",
            "https://no-location-support.example",
            "unsupported_set_location",
            {},
        ),
    ],
)
@deferred_f_from_coro_f
async def test_checker_location(postal_code, url, close_reason, stats, mockserver):
    """The default checker looks into the outcome of the ``setLocation`` action
    if a location meta/setting was used."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }
    if postal_code is not None:
        settings["ZYTE_API_SESSION_LOCATION"] = {"postalCode": postal_code}

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request(
                url,
                meta={
                    "zyte_api_automap": {
                        "actions": [
                            {
                                "action": "setLocation",
                                "address": {"postalCode": postal_code},
                            }
                        ]
                    },
                },
            )

        def parse(self, response):
            pass

        def closed(self, reason):
            self.close_reason = reason

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.spider.close_reason == close_reason
    assert_session_stats(crawler, stats)


def test_session_config_check_non_setlocation_action_first():
    crawler = scrapy_get_crawler(settings_dict={})
    config = SessionConfig(crawler)

    request = Request(
        "https://example.com",
        meta={"zyte_api_session_location": {"postalCode": "10001"}},
    )

    class MockResponse:
        raw_api_response = {
            "actions": [
                {"action": "click", "status": "success"},
                {"action": "setLocation", "status": "success"},
            ]
        }

    assert config.check(MockResponse(), request) is True
