from typing import Any, Dict

import pytest
from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.httpobj import urlparse_cached

from scrapy_zyte_api import LocationSessionConfig, session_config
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@deferred_f_from_coro_f
async def test_location_session_config(mockserver):
    pytest.importorskip("web_poet")

    @session_config(
        [
            "postal-code-10001.example",
            "postal-code-10001-fail.example",
            "postal-code-10001-alternative.example",
        ]
    )
    class CustomSessionConfig(LocationSessionConfig):
        def location_params(
            self, request: Request, location: Dict[str, Any]
        ) -> Dict[str, Any]:
            assert location == {"postalCode": "10002"}
            return {
                "actions": [
                    {
                        "action": "setLocation",
                        "address": {"postalCode": "10001"},
                    }
                ]
            }

        def location_check(
            self, response: Response, request: Request, location: Dict[str, Any]
        ) -> bool:
            assert location == {"postalCode": "10002"}
            domain = urlparse_cached(request).netloc
            return "fail" not in domain

        def pool(self, request: Request) -> str:
            domain = urlparse_cached(request).netloc
            if domain == "postal-code-10001-alternative.example":
                return "postal-code-10001.example"
            return domain

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        # We set a location to force the location-specific methods of the
        # session config class to be called, but we set the wrong location so
        # that the test would not pass were it not for our custom
        # implementation which ignores the input location and instead sets the
        # right one.
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10002"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://postal-code-10001.example",
            "https://postal-code-10001-alternative.example",
            "https://postal-code-10001-fail.example",
        ]

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
                                }
                            ]
                        },
                    },
                )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {
            "postal-code-10001.example": {
                "init/check-passed": 2,
                "use/check-passed": 2,
            },
            "postal-code-10001-fail.example": {"init/check-failed": 1},
        },
    )

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {
            "postal-code-10001.example": {"init/failed": 1},
            "postal-code-10001-alternative.example": {"init/failed": 1},
            "postal-code-10001-fail.example": {"init/failed": 1},
        },
    )


@deferred_f_from_coro_f
async def test_location_session_config_no_methods(mockserver):
    """If no location_* methods are defined, LocationSessionConfig works the
    same as SessionConfig."""
    pytest.importorskip("web_poet")

    @session_config(
        [
            "postal-code-10001.example",
            "postal-code-10001-alternative.example",
        ]
    )
    class CustomSessionConfig(LocationSessionConfig):
        def pool(self, request: Request) -> str:
            domain = urlparse_cached(request).netloc
            if domain == "postal-code-10001-alternative.example":
                return "postal-code-10001.example"
            return domain

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://postal-code-10001.example",
            "https://postal-code-10001-alternative.example",
        ]

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
                                }
                            ]
                        },
                    },
                )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {"postal-code-10001.example": {"init/check-passed": 2, "use/check-passed": 2}},
    )

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_location_session_config_no_location(mockserver):
    """If no location is configured, the methods are never called."""
    pytest.importorskip("web_poet")

    @session_config(["postal-code-10001.example", "a.example"])
    class CustomSessionConfig(LocationSessionConfig):
        def location_params(
            self, request: Request, location: Dict[str, Any]
        ) -> Dict[str, Any]:
            assert False

        def location_check(
            self, response: Response, request: Request, location: Dict[str, Any]
        ) -> bool:
            assert False

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example", "https://a.example"]

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
                                }
                            ]
                        },
                    },
                )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {
            "postal-code-10001.example": {"init/failed": 1},
            "a.example": {"init/check-passed": 1, "use/check-passed": 1},
        },
    )

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]
