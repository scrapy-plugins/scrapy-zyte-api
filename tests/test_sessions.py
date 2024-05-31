from typing import Any, Dict

import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider

from . import get_crawler


@pytest.mark.parametrize(
    ("setting", "meta", "outcome"),
    (
        (None, None, False),
        (None, True, True),
        (None, False, False),
        (True, None, True),
        (True, True, True),
        (True, False, False),
        (False, None, False),
        (False, True, True),
        (False, False, False),
    ),
)
@ensureDeferred
async def test_enabled(setting, meta, outcome, mockserver):
    settings = {"ZYTE_API_URL": mockserver.urljoin("/")}
    if setting is not None:
        settings["ZYTE_API_SESSION_ENABLED"] = setting
    meta_dict = {}
    if meta is not None:
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


@pytest.mark.parametrize(
    ("params_setting", "params_meta", "location_setting", "location_meta", "outcome"),
    (
        (None, None, None, None, False),
        (None, None, None, False, False),
        (None, None, None, True, True),
        (None, None, False, None, False),
        (None, None, False, False, False),
        (None, None, False, True, True),
        (None, None, True, None, True),
        (None, None, True, False, False),
        (None, None, True, True, True),
        (None, False, None, None, False),
        (None, False, None, False, False),
        (None, False, None, True, True),
        (None, False, False, None, False),
        (None, False, False, False, False),
        (None, False, False, True, True),
        (None, False, True, None, True),
        (None, False, True, False, False),
        (None, False, True, True, True),
        (None, True, None, None, True),
        (None, True, None, False, False),
        (None, True, None, True, True),
        (None, True, False, None, False),
        (None, True, False, False, False),
        (None, True, False, True, True),
        (None, True, True, None, True),
        (None, True, True, False, False),
        (None, True, True, True, True),
        (False, None, None, None, False),
        (False, None, None, False, False),
        (False, None, None, True, True),
        (False, None, False, None, False),
        (False, None, False, False, False),
        (False, None, False, True, True),
        (False, None, True, None, True),
        (False, None, True, False, False),
        (False, None, True, True, True),
        (False, False, None, None, False),
        (False, False, None, False, False),
        (False, False, None, True, True),
        (False, False, False, None, False),
        (False, False, False, False, False),
        (False, False, False, True, True),
        (False, False, True, None, True),
        (False, False, True, False, False),
        (False, False, True, True, True),
        (False, True, None, None, True),
        (False, True, None, False, False),
        (False, True, None, True, True),
        (False, True, False, None, False),
        (False, True, False, False, False),
        (False, True, False, True, True),
        (False, True, True, None, True),
        (False, True, True, False, False),
        (False, True, True, True, True),
        (True, None, None, None, True),
        (True, None, None, False, False),
        (True, None, None, True, True),
        (True, None, False, None, False),
        (True, None, False, False, False),
        (True, None, False, True, True),
        (True, None, True, None, True),
        (True, None, True, False, False),
        (True, None, True, True, True),
        (True, False, None, None, False),
        (True, False, None, False, False),
        (True, False, None, True, True),
        (True, False, False, None, False),
        (True, False, False, False, False),
        (True, False, False, True, True),
        (True, False, True, None, True),
        (True, False, True, False, False),
        (True, False, True, True, True),
        (True, True, None, None, True),
        (True, True, None, False, False),
        (True, True, None, True, True),
        (True, True, False, None, False),
        (True, True, False, False, False),
        (True, True, False, True, True),
        (True, True, True, None, True),
        (True, True, True, False, False),
        (True, True, True, True, True),
    ),
)
@ensureDeferred
async def test_param_precedence(
    params_setting, params_meta, location_setting, location_meta, outcome, mockserver
):
    postal_codes = {True: "10001", False: "10002"}
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_ENABLED": True,
    }
    meta: Dict[str, Any] = {}

    if params_setting is not None:
        settings["ZYTE_API_SESSION_PARAMS"] = {
            "actions": [
                {
                    "action": "setLocation",
                    "address": {"postalCode": postal_codes[params_setting]},
                }
            ]
        }
    if params_meta is not None:
        meta["zyte_api_session_params"] = {
            "actions": [
                {
                    "action": "setLocation",
                    "address": {"postalCode": postal_codes[params_meta]},
                }
            ]
        }
    if location_setting is not None:
        settings["ZYTE_API_SESSION_LOCATION"] = {
            "postalCode": postal_codes[location_setting]
        }
    if location_meta is not None:
        meta["zyte_api_session_location"] = {"postalCode": postal_codes[location_meta]}

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request(
                "https://postal-code-10001.example",
                meta={
                    "zyte_api_automap": {
                        "actions": [
                            {
                                "action": "setLocation",
                                "address": {"postalCode": postal_codes[True]},
                            }
                        ]
                    },
                    **meta,
                },
            )

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
            "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 1,
            "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 1,
        }
    else:
        assert session_stats == {
            "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/failed": 1,
        }
