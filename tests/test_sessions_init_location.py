import pytest
from scrapy import Request, Spider
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api import SessionConfig, session_config
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler


@pytest.mark.parametrize(
    ("settings", "meta", "used"),
    (
        ({}, {}, True),
        (
            {
                "ZYTE_API_SESSION_PARAMS": {
                    "actions": [
                        {"action": "setLocation", "address": {"postalCode": "10002"}}
                    ]
                }
            },
            {},
            False,
        ),
        ({"ZYTE_API_SESSION_LOCATION": {"postalCode": "10002"}}, {}, False),
        (
            {},
            {
                "zyte_api_session_params": {
                    "actions": [
                        {"action": "setLocation", "address": {"postalCode": "10002"}}
                    ]
                }
            },
            False,
        ),
        ({}, {"zyte_api_session_location": {"postalCode": "10002"}}, False),
    ),
)
@deferred_f_from_coro_f
async def test_session_config_location(settings, meta, used, mockserver):
    """Overriding location in SessionConfig, if done according to the docs,
    only has an effect when neither spider-level nor request-level variables
    are used to modify params."""
    pytest.importorskip("web_poet")

    @session_config(["postal-code-10001.example"])
    class CustomSessionConfig(SessionConfig):
        def location(self, request: Request):
            return super().location(request) or {"postalCode": "10001"}

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
    if used:
        assert session_stats == {
            "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 1,
            "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 1,
        }
    else:
        pool = (
            "postal-code-10001.example[0]"
            if "zyte_api_session_params" in meta
            else (
                "postal-code-10001.example@10002"
                if "zyte_api_session_location" in meta
                else "postal-code-10001.example"
            )
        )
        assert session_stats == {
            f"scrapy-zyte-api/sessions/pools/{pool}/init/failed": 1,
        }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("settings", "meta", "used"),
    (
        ({}, {}, True),
        (
            {
                "ZYTE_API_SESSION_PARAMS": {
                    "actions": [
                        {"action": "setLocation", "address": {"postalCode": "10002"}}
                    ]
                }
            },
            {},
            False,
        ),
        ({"ZYTE_API_SESSION_LOCATION": {"postalCode": "10002"}}, {}, True),
        (
            {},
            {
                "zyte_api_session_params": {
                    "actions": [
                        {"action": "setLocation", "address": {"postalCode": "10002"}}
                    ]
                }
            },
            False,
        ),
        ({}, {"zyte_api_session_location": {"postalCode": "10002"}}, True),
    ),
)
@deferred_f_from_coro_f
async def test_session_config_location_bad(settings, meta, used, mockserver):
    """Overriding location in SessionConfig, if it does not return
    super().location() when truthy, breaks params precedence for location meta
    key and setting, but does not break raw params meta key and setting."""
    pytest.importorskip("web_poet")

    @session_config(["postal-code-10001.example"])
    class CustomSessionConfig(SessionConfig):
        def location(self, request: Request):
            return {"postalCode": "10001"}

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
    pool = (
        "postal-code-10001.example[0]"
        if "zyte_api_session_params" in meta
        else (
            "postal-code-10001.example@10002"
            if "zyte_api_session_location" in meta
            else "postal-code-10001.example"
        )
    )
    if used:
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


@deferred_f_from_coro_f
async def test_session_config_params_location(mockserver):
    """A custom session config can be used to customize the params for
    location, e.g. to include extra actions, while still relying on the default
    check to determine whether or not the session remains valid based on the
    outcome of the ``setLocation`` action."""
    pytest.importorskip("web_poet")

    @session_config(["postal-code-10001.example"])
    class CustomSessionConfig(SessionConfig):
        def params(self, request: Request):
            return {
                "actions": [
                    {
                        "action": "waitForNavigation",
                    },
                    {
                        "action": "setLocation",
                        "address": self.location(request),
                    },
                ]
            }

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
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
                                }
                            ]
                        },
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
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_session_config_params_location_no_set_location(mockserver):
    """A custom session config can be used to customize the params for
    location to the point where they do not use a ``setLocation`` action. In
    that case, the default session check will return ``True`` by default, i.e.
    it will not fail due to not finding ``setLocation`` in response actions
    data."""
    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        def params(self, request: Request):
            postal_code = self.location(request)["postalCode"]
            return {
                "actions": [
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": f"#zip{postal_code}"},
                    },
                ]
            }

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

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]
