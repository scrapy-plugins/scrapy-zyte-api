from collections import deque
from copy import copy
from math import floor
from typing import Any, Dict
from unittest.mock import patch

import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider, signals
from scrapy.exceptions import CloseSpider
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached
from zyte_api import RequestError

from scrapy_zyte_api import (
    SESSION_AGGRESSIVE_RETRY_POLICY,
    SESSION_DEFAULT_RETRY_POLICY,
    SessionConfig,
    session_config,
)
from scrapy_zyte_api.utils import _RAW_CLASS_SETTING_SUPPORT, _REQUEST_ERROR_HAS_QUERY

from . import get_crawler, serialize_settings

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
        (UNSET, False, UNSET, True, True),
        (UNSET, False, False, UNSET, False),
        (UNSET, False, False, None, False),
        (UNSET, False, False, False, False),
        (UNSET, False, False, True, True),
        (UNSET, False, True, UNSET, True),
        (UNSET, False, True, None, False),
        (UNSET, False, True, False, False),
        (UNSET, False, True, True, True),
        (UNSET, True, UNSET, UNSET, True),
        (UNSET, True, UNSET, None, True),
        (UNSET, True, UNSET, False, False),
        (UNSET, True, UNSET, True, True),
        (UNSET, True, False, UNSET, False),
        (UNSET, True, False, None, True),
        (UNSET, True, False, False, False),
        (UNSET, True, False, True, True),
        (UNSET, True, True, UNSET, True),
        (UNSET, True, True, None, True),
        (UNSET, True, True, False, False),
        (UNSET, True, True, True, True),
        (False, UNSET, UNSET, UNSET, False),
        (False, UNSET, UNSET, None, False),
        (False, UNSET, UNSET, False, False),
        (False, UNSET, UNSET, True, True),
        (False, UNSET, False, UNSET, False),
        (False, UNSET, False, None, False),
        (False, UNSET, False, False, False),
        (False, UNSET, False, True, True),
        (False, UNSET, True, UNSET, True),
        (False, UNSET, True, None, False),
        (False, UNSET, True, False, False),
        (False, UNSET, True, True, True),
        (False, False, UNSET, UNSET, False),
        (False, False, UNSET, None, False),
        (False, False, UNSET, False, False),
        (False, False, UNSET, True, True),
        (False, False, False, UNSET, False),
        (False, False, False, None, False),
        (False, False, False, False, False),
        (False, False, False, True, True),
        (False, False, True, UNSET, True),
        (False, False, True, None, False),
        (False, False, True, False, False),
        (False, False, True, True, True),
        (False, True, UNSET, UNSET, True),
        (False, True, UNSET, None, True),
        (False, True, UNSET, False, False),
        (False, True, UNSET, True, True),
        (False, True, False, UNSET, False),
        (False, True, False, None, True),
        (False, True, False, False, False),
        (False, True, False, True, True),
        (False, True, True, UNSET, True),
        (False, True, True, None, True),
        (False, True, True, False, False),
        (False, True, True, True, True),
        (True, UNSET, UNSET, UNSET, True),
        (True, UNSET, UNSET, None, True),
        (True, UNSET, UNSET, False, False),
        (True, UNSET, UNSET, True, True),
        (True, UNSET, False, UNSET, False),
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
        (True, False, UNSET, True, True),
        (True, False, False, UNSET, False),
        (True, False, False, None, False),
        (True, False, False, False, False),
        (True, False, False, True, True),
        (True, False, True, UNSET, True),
        (True, False, True, None, False),
        (True, False, True, False, False),
        (True, False, True, True, True),
        (True, True, UNSET, UNSET, True),
        (True, True, UNSET, None, True),
        (True, True, UNSET, False, False),
        (True, True, UNSET, True, True),
        (True, True, False, UNSET, False),
        (True, True, False, None, True),
        (True, True, False, False, False),
        (True, True, False, True, True),
        (True, True, True, UNSET, True),
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
        "ZYTE_API_SESSION_ENABLED": True,
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


@pytest.mark.parametrize(
    ("params", "close_reason", "stats"),
    (
        (
            {"browserHtml": True},
            "bad_session_inits",
            {
                "scrapy-zyte-api/sessions/pools/forbidden.example/init/failed": 1,
            },
        ),
        (
            {"browserHtml": True, "url": "https://example.com"},
            "failed_forbidden_domain",
            {
                "scrapy-zyte-api/sessions/pools/forbidden.example/init/check-passed": 2,
                "scrapy-zyte-api/sessions/pools/forbidden.example/use/failed": 1,
            },
        ),
    ),
)
@ensureDeferred
async def test_url_override(params, close_reason, stats, mockserver):
    """If session params define a URL, that URL is used for session
    initialization. Otherwise, the URL from the request getting the session
    assigned first is used for session initialization."""
    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_PARAMS": params,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://forbidden.example"]

        def parse(self, response):
            pass

        def closed(self, reason):
            self.close_reason = reason

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert crawler.spider.close_reason == close_reason
    assert session_stats == stats


class ConstantChecker:

    def __init__(self, result):
        self._result = result

    def check(self, request: Request, response: Response) -> bool:
        if self._result in (True, False):
            return self._result
        raise self._result


class TrueChecker(ConstantChecker):
    def __init__(self):
        super().__init__(True)


class FalseChecker(ConstantChecker):
    def __init__(self):
        super().__init__(False)


class CloseSpiderChecker(ConstantChecker):
    def __init__(self):
        super().__init__(CloseSpider("checker_failed"))


class TrueCrawlerChecker(ConstantChecker):
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        super().__init__(crawler.settings["ZYTE_API_SESSION_ENABLED"])


class FalseCrawlerChecker(ConstantChecker):
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        super().__init__(not crawler.settings["ZYTE_API_SESSION_ENABLED"])


@pytest.mark.parametrize(
    ("checker", "close_reason", "stats"),
    (
        *(
            pytest.param(
                checker,
                close_reason,
                stats,
                marks=pytest.mark.skipif(
                    not _RAW_CLASS_SETTING_SUPPORT,
                    reason=(
                        "Configuring component classes instead of their import "
                        "paths requires Scrapy 2.4+."
                    ),
                ),
            )
            for checker, close_reason, stats in (
                (
                    TrueChecker,
                    "finished",
                    {
                        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
                        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
                    },
                ),
                (
                    FalseChecker,
                    "bad_session_inits",
                    {"scrapy-zyte-api/sessions/pools/example.com/init/check-failed": 1},
                ),
                (CloseSpiderChecker, "checker_failed", {}),
                (
                    TrueCrawlerChecker,
                    "finished",
                    {
                        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
                        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
                    },
                ),
                (
                    FalseCrawlerChecker,
                    "bad_session_inits",
                    {"scrapy-zyte-api/sessions/pools/example.com/init/check-failed": 1},
                ),
            )
        ),
        (
            "tests.test_sessions.TrueChecker",
            "finished",
            {
                "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
                "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
            },
        ),
        (
            "tests.test_sessions.FalseChecker",
            "bad_session_inits",
            {"scrapy-zyte-api/sessions/pools/example.com/init/check-failed": 1},
        ),
        ("tests.test_sessions.CloseSpiderChecker", "checker_failed", {}),
        (
            "tests.test_sessions.TrueCrawlerChecker",
            "finished",
            {
                "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
                "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
            },
        ),
        (
            "tests.test_sessions.FalseCrawlerChecker",
            "bad_session_inits",
            {"scrapy-zyte-api/sessions/pools/example.com/init/check-failed": 1},
        ),
    ),
)
@ensureDeferred
async def test_checker(checker, close_reason, stats, mockserver):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": checker,
        "ZYTE_API_SESSION_ENABLED": True,
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
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert crawler.spider.close_reason == close_reason
    assert session_stats == stats


@pytest.mark.parametrize(
    ("postal_code", "url", "close_reason", "stats"),
    (
        (
            None,
            "https://example.com",
            "finished",
            {
                "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
                "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
            },
        ),
        (
            "10001",
            "https://postal-code-10001.example",
            "finished",
            {
                "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 1,
                "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 1,
            },
        ),
        (
            "10002",
            "https://postal-code-10001.example",
            "bad_session_inits",
            {"scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/failed": 1},
        ),
        (
            "10001",
            "https://no-location-support.example",
            "unsupported_set_location",
            {},
        ),
    ),
)
@ensureDeferred
async def test_checker_location(postal_code, url, close_reason, stats, mockserver):
    """The default checker looks into the outcome of the ``setLocation`` action
    if a location meta/setting was used."""
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }
    if postal_code is not None:
        settings["ZYTE_API_SESSION_LOCATION"] = {"postalCode": postal_code}

    class TestSpider(Spider):
        name = "test"

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
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert crawler.spider.close_reason == close_reason
    assert session_stats == stats


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        (0, 1),
        (1, 1),
        (2, 2),
        (None, 8),
    ),
)
@ensureDeferred
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
    await crawler.crawl()

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
@ensureDeferred
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
    await crawler.crawl()

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


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        (None, 1),
        (0, 1),
        (1, 1),
        (2, 2),
    ),
)
@ensureDeferred
async def test_max_errors(setting, value, mockserver):
    retry_times = 2
    settings = {
        "RETRY_TIMES": retry_times,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_PARAMS": {"browserHtml": True},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }
    if setting is not None:
        settings["ZYTE_API_SESSION_MAX_ERRORS"] = setting

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com/"]

        def start_requests(self):
            for url in self.start_urls:
                yield Request(
                    url,
                    meta={
                        "zyte_api_automap": {
                            "browserHtml": True,
                            "httpResponseBody": True,
                        }
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
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": floor(
            (retry_times + 1) / value
        )
        + 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/failed": retry_times + 1,
    }


class DomainChecker:

    def check(self, request: Request, response: Response) -> bool:
        domain = urlparse_cached(request).netloc
        return "fail" not in domain


@ensureDeferred
async def test_check_overrides_error(mockserver):
    """Max errors are ignored if a session does not pass its session check."""
    retry_times = 2
    settings = {
        "RETRY_TIMES": retry_times,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions.DomainChecker",
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_ERRORS": 2,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-check-fails.example"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/init/check-passed": retry_times
        + 2,
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/use/check-failed": retry_times
        + 1,
    }


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        (1, 1),
        (2, 2),
        (None, 8),
    ),
)
@ensureDeferred
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
    await crawler.crawl()

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
@ensureDeferred
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
    await crawler.crawl()

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


def mock_request_error(*, status=200):
    kwargs: Dict[str, Any] = {}
    if _REQUEST_ERROR_HAS_QUERY:
        kwargs["query"] = {}
    return RequestError(
        history=None,
        request_info=None,
        response_content=None,
        status=status,
        **kwargs,
    )


# Number of times to test request errors that must be retried forever.
FOREVER_TIMES = 100


class fast_forward:
    def __init__(self, time):
        self.time = time


@pytest.mark.parametrize(
    ("retrying", "outcomes", "exhausted"),
    (
        *(
            (retry_policy, outcomes, exhausted)
            for retry_policy in (
                SESSION_DEFAULT_RETRY_POLICY,
                SESSION_AGGRESSIVE_RETRY_POLICY,
            )
            for status in (520, 521)
            for outcomes, exhausted in (
                (
                    (mock_request_error(status=status),),
                    True,
                ),
                (
                    (mock_request_error(status=429),),
                    False,
                ),
                (
                    (
                        mock_request_error(status=429),
                        mock_request_error(status=status),
                    ),
                    True,
                ),
            )
        ),
    ),
)
@ensureDeferred
@patch("time.monotonic")
async def test_retry_stop(monotonic_mock, retrying, outcomes, exhausted):
    monotonic_mock.return_value = 0
    last_outcome = outcomes[-1]
    outcomes = deque(outcomes)

    def wait(retry_state):
        return 0.0

    retrying = copy(retrying)
    retrying.wait = wait

    async def run():
        while True:
            try:
                outcome = outcomes.popleft()
            except IndexError:
                return
            else:
                if isinstance(outcome, fast_forward):
                    monotonic_mock.return_value += outcome.time
                    continue
                raise outcome

    run = retrying.wraps(run)
    try:
        await run()
    except Exception as outcome:
        assert exhausted
        assert outcome is last_outcome
    else:
        assert not exhausted


try:
    from scrapy import addons  # noqa: F401
except ImportError:
    ADDON_SUPPORT = False
else:
    ADDON_SUPPORT = True


@pytest.mark.parametrize(
    ("manual_settings", "addon_settings"),
    (
        (
            {"ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY"},
            {},
        ),
        (
            {"ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY"},
            {"ZYTE_API_RETRY_POLICY": "zyte_api.zyte_api_retrying"},
        ),
        (
            {
                "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY"
            },
            {"ZYTE_API_RETRY_POLICY": "zyte_api.aggressive_retrying"},
        ),
        (
            {"ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY"},
            {"ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY"},
        ),
        (
            {
                "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY"
            },
            {
                "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY"
            },
        ),
        (
            {"ZYTE_API_RETRY_POLICY": "tests.test_sessions.UNSET"},
            {"ZYTE_API_RETRY_POLICY": "tests.test_sessions.UNSET"},
        ),
    ),
)
@ensureDeferred
@pytest.mark.skipif(
    not ADDON_SUPPORT, reason="No add-on support in this version of Scrapy"
)
async def test_addon(manual_settings, addon_settings):
    crawler = await get_crawler(
        {
            "ZYTE_API_TRANSPARENT_MODE": True,
            "ZYTE_API_SESSION_ENABLED": True,
            **manual_settings,
        }
    )
    addon_crawler = await get_crawler(
        {"ZYTE_API_SESSION_ENABLED": True, **addon_settings}, use_addon=True
    )
    assert serialize_settings(crawler.settings) == serialize_settings(
        addon_crawler.settings
    )


@ensureDeferred
async def test_session_config(mockserver):
    pytest.importorskip("web_poet")

    @session_config("postal-code-10001-a.example")
    class CustomSessionConfig(SessionConfig):

        def params(self, request: Request):
            return {
                "actions": [
                    {
                        "action": "setLocation",
                        "address": {"postalCode": "10001"},
                    }
                ]
            }

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://postal-code-10001-a.example",
            "https://postal-code-10001-b.example",
        ]

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
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/use/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-b.example/init/failed": 1,
    }

    # Clean up the session config registry, and check it, otherwese we could
    # affect other tests.

    from scrapy_zyte_api._session import session_config_registry

    session_config_registry.__init__()  # type: ignore[misc]

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-b.example/init/failed": 1,
    }


@ensureDeferred
async def test_session_refresh(mockserver):
    """When a session fails to pass its validity check, the session is
    discarded and a different session is used instead."""

    class Tracker:
        def __init__(self):
            self.sessions = []

        def track_session(self, request: Request, spider: Spider):
            self.sessions.append(request.meta["zyte_api"]["session"]["id"])

    tracker = Tracker()

    settings = {
        "RETRY_TIMES": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions.DomainChecker",
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://session-check-fails.example"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(
        tracker.track_session, signal=signals.request_reached_downloader
    )
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/init/check-passed": 3,
        "scrapy-zyte-api/sessions/pools/session-check-fails.example/use/check-failed": 2,
    }
    assert len(tracker.sessions) == 5
    assert tracker.sessions[0] == tracker.sessions[1]
    assert tracker.sessions[0] != tracker.sessions[2]
    assert tracker.sessions[2] == tracker.sessions[3]
    assert tracker.sessions[0] != tracker.sessions[4]
    assert tracker.sessions[2] != tracker.sessions[4]
