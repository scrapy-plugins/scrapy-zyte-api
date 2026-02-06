from typing import Any, Dict

import pytest
from scrapy import Request, Spider
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api import SessionConfig, session_config
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler, UNSET


@pytest.mark.parametrize(
    ("params_setting", "params_meta", "location_setting", "location_meta", "outcome"),
    (
        (UNSET, UNSET, UNSET, UNSET, False),
        (UNSET, UNSET, UNSET, None, False),
        (UNSET, UNSET, UNSET, False, False),
        (UNSET, UNSET, UNSET, True, True),
        (UNSET, UNSET, False, UNSET, False),
        (UNSET, UNSET, False, None, False),
        (UNSET, UNSET, False, False, False),
        (UNSET, UNSET, False, True, True),
        (UNSET, UNSET, True, UNSET, True),
        (UNSET, UNSET, True, None, False),
        (UNSET, UNSET, True, False, False),
        (UNSET, UNSET, True, True, True),
        (UNSET, False, UNSET, UNSET, False),
        (UNSET, False, UNSET, None, False),
        (UNSET, False, UNSET, False, False),
        (UNSET, False, UNSET, True, False),
        (UNSET, False, False, UNSET, False),
        (UNSET, False, False, None, False),
        (UNSET, False, False, False, False),
        (UNSET, False, False, True, False),
        (UNSET, False, True, UNSET, False),
        (UNSET, False, True, None, False),
        (UNSET, False, True, False, False),
        (UNSET, False, True, True, False),
        (UNSET, True, UNSET, UNSET, True),
        (UNSET, True, UNSET, None, True),
        (UNSET, True, UNSET, False, True),
        (UNSET, True, UNSET, True, True),
        (UNSET, True, False, UNSET, True),
        (UNSET, True, False, None, True),
        (UNSET, True, False, False, True),
        (UNSET, True, False, True, True),
        (UNSET, True, True, UNSET, True),
        (UNSET, True, True, None, True),
        (UNSET, True, True, False, True),
        (UNSET, True, True, True, True),
        (False, UNSET, UNSET, UNSET, False),
        (False, UNSET, UNSET, None, False),
        (False, UNSET, UNSET, False, False),
        (False, UNSET, UNSET, True, True),
        (False, UNSET, False, UNSET, False),
        (False, UNSET, False, None, False),
        (False, UNSET, False, False, False),
        (False, UNSET, False, True, True),
        (False, UNSET, True, UNSET, False),
        (False, UNSET, True, None, False),
        (False, UNSET, True, False, False),
        (False, UNSET, True, True, True),
        (False, False, UNSET, UNSET, False),
        (False, False, UNSET, None, False),
        (False, False, UNSET, False, False),
        (False, False, UNSET, True, False),
        (False, False, False, UNSET, False),
        (False, False, False, None, False),
        (False, False, False, False, False),
        (False, False, False, True, False),
        (False, False, True, UNSET, False),
        (False, False, True, None, False),
        (False, False, True, False, False),
        (False, False, True, True, False),
        (False, True, UNSET, UNSET, True),
        (False, True, UNSET, None, True),
        (False, True, UNSET, False, True),
        (False, True, UNSET, True, True),
        (False, True, False, UNSET, True),
        (False, True, False, None, True),
        (False, True, False, False, True),
        (False, True, False, True, True),
        (False, True, True, UNSET, True),
        (False, True, True, None, True),
        (False, True, True, False, True),
        (False, True, True, True, True),
        (True, UNSET, UNSET, UNSET, True),
        (True, UNSET, UNSET, None, True),
        (True, UNSET, UNSET, False, False),
        (True, UNSET, UNSET, True, True),
        (True, UNSET, False, UNSET, True),
        (True, UNSET, False, None, True),
        (True, UNSET, False, False, False),
        (True, UNSET, False, True, True),
        (True, UNSET, True, UNSET, True),
        (True, UNSET, True, None, True),
        (True, UNSET, True, False, False),
        (True, UNSET, True, True, True),
        (True, False, UNSET, UNSET, False),
        (True, False, UNSET, None, False),
        (True, False, UNSET, False, False),
        (True, False, UNSET, True, False),
        (True, False, False, UNSET, False),
        (True, False, False, None, False),
        (True, False, False, False, False),
        (True, False, False, True, False),
        (True, False, True, UNSET, False),
        (True, False, True, None, False),
        (True, False, True, False, False),
        (True, False, True, True, False),
        (True, True, UNSET, UNSET, True),
        (True, True, UNSET, None, True),
        (True, True, UNSET, False, True),
        (True, True, UNSET, True, True),
        (True, True, False, UNSET, True),
        (True, True, False, None, True),
        (True, True, False, False, True),
        (True, True, False, True, True),
        (True, True, True, UNSET, True),
        (True, True, True, None, True),
        (True, True, True, False, True),
        (True, True, True, True, True),
    ),
)
@deferred_f_from_coro_f
async def test_params_precedence(
    params_setting, params_meta, location_setting, location_meta, outcome, mockserver
):
    postal_codes = {True: "10001", False: "10002"}
    pool = (
        "postal-code-10001.example[0]"
        if params_meta in postal_codes
        else (
            f"postal-code-10001.example@{postal_codes[location_meta]}"
            if location_meta in postal_codes
            else "postal-code-10001.example"
        )
    )
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }
    meta: Dict[str, Any] = {}

    if params_setting is not UNSET:
        settings["ZYTE_API_SESSION_PARAMS"] = {
            "actions": [
                {
                    "action": "setLocation",
                    "address": {"postalCode": postal_codes[params_setting]},
                }
            ]
        }
    if params_meta is not UNSET:
        meta["zyte_api_session_params"] = {
            "actions": [
                {
                    "action": "setLocation",
                    "address": {"postalCode": postal_codes[params_meta]},
                }
            ]
        }
    if location_setting is not UNSET:
        settings["ZYTE_API_SESSION_LOCATION"] = {
            "postalCode": postal_codes[location_setting]
        }
    if location_meta is None:
        meta["zyte_api_session_location"] = {}
    elif location_meta is not UNSET:
        meta["zyte_api_session_location"] = {"postalCode": postal_codes[location_meta]}

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

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
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    if outcome:
        assert session_stats == {
            f"scrapy-zyte-api/sessions/pools/{pool}/init/check-passed": 1,
            f"scrapy-zyte-api/sessions/pools/{pool}/use/check-passed": 1,
        }
    else:
        assert session_stats == {
            f"scrapy-zyte-api/sessions/pools/{pool}/init/failed": 1,
        }


@pytest.mark.parametrize(
    ("meta", "settings", "pool", "outcome"),
    (
        ({}, {}, "postal-code-10001.example", False),
        (
            {
                "zyte_api_session_params": {
                    "actions": [
                        {
                            "action": "setLocation",
                            "address": {"postalCode": "10001"},
                        },
                    ]
                }
            },
            {},
            "postal-code-10001.example[0]",
            True,
        ),
        (
            {"zyte_api_session_location": {"postalCode": "10001"}},
            {},
            "postal-code-10001.example@10001",
            False,
        ),
        (
            {},
            {
                "ZYTE_API_SESSION_PARAMS": {
                    "actions": [
                        {
                            "action": "setLocation",
                            "address": {"postalCode": "10001"},
                        },
                    ]
                }
            },
            "postal-code-10001.example",
            True,
        ),
        (
            {},
            {"ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"}},
            "postal-code-10001.example",
            False,
        ),
    ),
)
@deferred_f_from_coro_f
async def test_session_config_params_precedence(
    meta, settings, pool, outcome, mockserver
):
    """A params override should have no impact on the use of the
    zyte_api_session_params request metadata key or the use of the
    ZYTE_API_SESSION_PARAMS setting. However, it can nullify locations if not
    implemented with support for them as the default implementation has."""
    pytest.importorskip("web_poet")

    @session_config(["postal-code-10001.example"])
    class CustomSessionConfig(SessionConfig):
        def params(self, request: Request):
            return {
                "actions": [
                    {
                        "action": "setLocation",
                        "address": {"postalCode": "10002"},
                    },
                ]
            }

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        **settings,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example"]

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            for url in self.start_urls:
                yield Request(
                    url,
                    meta={
                        "zyte_api_automap": {
                            "actions": [
                                {
                                    "action": "setLocation",
                                    "address": {"postalCode": "10001"},
                                },
                            ],
                        },
                        **meta,
                    },
                )

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
            f"scrapy-zyte-api/sessions/pools/{pool}/init/check-passed": 1,
            f"scrapy-zyte-api/sessions/pools/{pool}/use/check-passed": 1,
        }
    else:
        assert session_stats == {
            f"scrapy-zyte-api/sessions/pools/{pool}/init/failed": 1,
        }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]
