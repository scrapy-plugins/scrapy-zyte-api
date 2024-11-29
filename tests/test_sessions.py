from collections import deque
from copy import copy, deepcopy
from math import floor
from typing import Any, Dict, Tuple, Union
from unittest.mock import patch

import pytest
from aiohttp.client_exceptions import ServerConnectionError
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider, signals
from scrapy.exceptions import CloseSpider
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from zyte_api import RequestError

from scrapy_zyte_api import (
    SESSION_AGGRESSIVE_RETRY_POLICY,
    SESSION_DEFAULT_RETRY_POLICY,
    LocationSessionConfig,
    SessionConfig,
    is_session_init_request,
    session_config,
)
from scrapy_zyte_api._session import SESSION_INIT_META_KEY, session_config_registry
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
        assert session_stats == {
            "scrapy-zyte-api/sessions/use/disabled": 1,
        }


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
@ensureDeferred
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
            f"scrapy-zyte-api/sessions/pools/{pool}/init/check-passed": 1,
            f"scrapy-zyte-api/sessions/pools/{pool}/use/check-passed": 1,
        }
    else:
        assert session_stats == {
            f"scrapy-zyte-api/sessions/pools/{pool}/init/failed": 1,
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
                "scrapy-zyte-api/sessions/pools/forbidden.example/init/check-passed": 1,
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

    def check(self, response: Response, request: Request) -> bool:
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
        super().__init__(CloseSpider("closed_by_checker"))


class UnexpectedExceptionChecker(ConstantChecker):
    def __init__(self):
        super().__init__(Exception)


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


class UseChecker(ConstantChecker):
    """Always pass for session initialization requests, apply the check logic
    only on session use requests."""

    def check(self, response: Response, request: Request) -> bool:
        if response.meta.get(SESSION_INIT_META_KEY, False) is True:
            return True
        return super().check(response, request)


class FalseUseChecker(FalseChecker, UseChecker):
    pass


class CloseSpiderUseChecker(CloseSpiderChecker, UseChecker):
    pass


class UnexpectedExceptionUseChecker(UnexpectedExceptionChecker, UseChecker):
    pass


class OnlyPassFirstInitChecker:

    def __init__(self):
        self.on_first_init = True

    def check(self, response: Response, request: Request) -> bool:
        if self.on_first_init:
            self.on_first_init = False
            return True
        return False


# NOTE: There is no use checker subclass for TrueChecker because the outcome
# would be the same (always return True), and there are no use checker
# subclasses for the crawler classes because the init use is enough to verify
# that using the crawler works.

CHECKER_TESTS: Tuple[Tuple[str, str, Dict[str, int]], ...] = (
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
    (
        "tests.test_sessions.FalseUseChecker",
        "finished",
        {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 2,
            "scrapy-zyte-api/sessions/pools/example.com/use/check-failed": 1,
        },
    ),
    ("tests.test_sessions.CloseSpiderChecker", "closed_by_checker", {}),
    (
        "tests.test_sessions.CloseSpiderUseChecker",
        "closed_by_checker",
        {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        },
    ),
    (
        "tests.test_sessions.UnexpectedExceptionChecker",
        "bad_session_inits",
        {"scrapy-zyte-api/sessions/pools/example.com/init/check-error": 1},
    ),
    (
        "tests.test_sessions.UnexpectedExceptionUseChecker",
        "finished",
        {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 2,
            "scrapy-zyte-api/sessions/pools/example.com/use/check-error": 1,
        },
    ),
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
    (
        "tests.test_sessions.OnlyPassFirstInitChecker",
        "bad_session_inits",
        {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
            "scrapy-zyte-api/sessions/pools/example.com/init/check-failed": 1,
            "scrapy-zyte-api/sessions/pools/example.com/use/check-failed": 1,
        },
    ),
)


@pytest.mark.parametrize(
    ("checker", "close_reason", "stats"),
    (
        *CHECKER_TESTS,
        *(
            pytest.param(
                load_object(checker),
                close_reason,
                stats,
                marks=pytest.mark.skipif(
                    not _RAW_CLASS_SETTING_SUPPORT,
                    reason=(
                        "Configuring component classes instead of their "
                        "import paths requires Scrapy 2.4+."
                    ),
                ),
            )
            for checker, close_reason, stats in CHECKER_TESTS
        ),
    ),
)
@ensureDeferred
async def test_checker(checker, close_reason, stats, mockserver):
    settings = {
        "RETRY_TIMES": 0,
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
            "https://postal-code-10001-soft.example",
            "finished",
            {
                "scrapy-zyte-api/sessions/pools/postal-code-10001-soft.example/init/check-passed": 1,
                "scrapy-zyte-api/sessions/pools/postal-code-10001-soft.example/use/check-passed": 1,
            },
        ),
        (
            "10001",
            "https://postal-code-10001-soft.example",
            "finished",
            {
                "scrapy-zyte-api/sessions/pools/postal-code-10001-soft.example/init/check-passed": 1,
                "scrapy-zyte-api/sessions/pools/postal-code-10001-soft.example/use/check-passed": 1,
            },
        ),
        (
            "10002",
            "https://postal-code-10001-soft.example",
            "bad_session_inits",
            {
                "scrapy-zyte-api/sessions/pools/postal-code-10001-soft.example/init/check-failed": 1
            },
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


class CloseSpiderURLChecker:

    def check(self, response: Response, request: Request) -> bool:
        if "fail" in request.url:
            raise CloseSpider("closed_by_checker")
        return True


@ensureDeferred
async def test_checker_close_spider_use(mockserver):
    """A checker can raise CloseSpider not only during session initialization,
    but also during session use."""
    settings = {
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions.CloseSpiderURLChecker",
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com/fail"]

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
    assert crawler.spider.close_reason == "closed_by_checker"
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
    }


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
        "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY",
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    if setting is not None:
        settings["ZYTE_API_SESSION_MAX_ERRORS"] = setting

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://temporary-download-error.example"]

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
        "scrapy-zyte-api/sessions/pools/temporary-download-error.example/init/check-passed": floor(
            (retry_times + 1) / value
        )
        + 1,
        "scrapy-zyte-api/sessions/pools/temporary-download-error.example/use/failed": retry_times
        + 1,
    }


class DomainChecker:

    def check(self, response: Response, request: Request) -> bool:
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
    ("meta", "pool"),
    (
        ({}, "example.com"),
        ({"zyte_api_session_location": {"postalCode": "10001"}}, "example.com@10001"),
        (
            {"zyte_api_session_location": {"postalCode": "10001", "foo": "bar"}},
            "example.com@10001",
        ),
        (
            {
                "zyte_api_session_location": {
                    "addressCountry": "US",
                    "addressRegion": "TX",
                }
            },
            "example.com@US,TX",
        ),
        (
            {
                "zyte_api_session_location": {
                    "addressCountry": "ES",
                    "addressRegion": "Pontevedra",
                    "streetAddress": "Rúa do Príncipe, 123",
                    "postalCode": "12345",
                }
            },
            "example.com@ES,Pontevedra,12345,Rúa do Príncipe, 123",
        ),
        (
            {
                "zyte_api_session_params": {"foo": "bar"},
                "zyte_api_session_location": {"postalCode": "10001"},
            },
            "example.com[0]",
        ),
        (
            {
                "zyte_api_session_pool": "foo",
                "zyte_api_session_params": {"foo": "bar"},
                "zyte_api_session_location": {"postalCode": "10001"},
            },
            "foo",
        ),
    ),
)
@ensureDeferred
async def test_pool(meta, pool, mockserver):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
    }

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request("https://example.com", meta=meta)

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
        f"scrapy-zyte-api/sessions/pools/{pool}/init/check-passed": 1,
        f"scrapy-zyte-api/sessions/pools/{pool}/use/check-passed": 1,
    }


@ensureDeferred
async def test_pool_params(mockserver, caplog):
    settings = {
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request(
                "https://example.com/a",
                meta={"zyte_api_session_params": {"foo": "bar"}},
            )
            yield Request(
                "https://example.com/b",
                meta={"zyte_api_session_params": {"foo": "bar"}},
            )
            yield Request(
                "https://example.com/c",
                meta={"zyte_api_session_params": {"foo": "baz"}},
            )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    caplog.clear()
    caplog.set_level("INFO")
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com[0]/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com[0]/use/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/example.com[1]/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com[1]/use/check-passed": 1,
    }
    expected_logs = {
        (
            "INFO",
            "Session pool example.com[0] uses these session initialization parameters: {'foo': 'bar'}",
        ): 0,
        (
            "INFO",
            "Session pool example.com[1] uses these session initialization parameters: {'foo': 'baz'}",
        ): 0,
    }
    for record in caplog.records:
        entry = (record.levelname, record.msg)
        if entry in expected_logs:
            expected_logs[entry] += 1
    assert all(v == 1 for v in expected_logs.values())


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


def mock_request_error(*, status=200, response_content=None):
    kwargs: Dict[str, Any] = {}
    if _REQUEST_ERROR_HAS_QUERY:
        kwargs["query"] = {}
    return RequestError(
        history=None,
        request_info=None,
        response_content=response_content,
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

    @session_config(
        [
            "postal-code-10001-a.example",
            "postal-code-10001-a-fail.example",
            "postal-code-10001-a-alternative.example",
        ]
    )
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

        def check(self, response: Response, request: Request) -> bool:
            domain = urlparse_cached(request).netloc
            return "fail" not in domain

        def pool(self, request: Request) -> str:
            domain = urlparse_cached(request).netloc
            if domain == "postal-code-10001-a-alternative.example":
                return "postal-code-10001-a.example"
            return domain

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
            "https://postal-code-10001-a-alternative.example",
            "https://postal-code-10001-a-fail.example",
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
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/init/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/use/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a-fail.example/init/check-failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-b.example/init/failed": 1,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

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
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a-alternative.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a-fail.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-b.example/init/failed": 1,
    }


@ensureDeferred
async def test_session_config_check_meta(mockserver):
    """When initializing a session, known zyte_api_session-prefixed params
    should be included in the session initialization request, so that they can
    be used from check methods validating those requests.

    For example, when validating a location, access to
    zyte_api_session_location may be necessary.
    """
    pytest.importorskip("web_poet")

    params = {
        "actions": [
            {
                "action": "setLocation",
                "address": {"postalCode": "10001"},
            }
        ]
    }

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):

        def check(self, response, request):
            return (
                bool(self.location(request))
                and response.meta["zyte_api_session_params"] == params
                and (
                    (
                        response.meta.get("_is_session_init_request", False)
                        and "zyte_api_session_foo" not in response.meta
                    )
                    or response.meta["zyte_api_session_foo"] == "bar"
                )
            )

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def start_requests(self):
            for url in self.start_urls:
                yield Request(
                    url,
                    meta={
                        "zyte_api_automap": params,
                        "zyte_api_session_params": params,
                        "zyte_api_session_location": {"postalCode": "10001"},
                        "zyte_api_session_foo": "bar",
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
        "scrapy-zyte-api/sessions/pools/example.com[0]/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com[0]/use/check-passed": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


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
    await crawler.crawl()

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
@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        **settings,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example"]

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
    await crawler.crawl()

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
@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        **settings,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example"]

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
    await crawler.crawl()

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


@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example"]

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
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

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
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


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
@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        **settings,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example"]

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
    await crawler.crawl()

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


@ensureDeferred
async def test_session_config_params_error(mockserver):
    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):

        def params(self, request: Request):
            raise Exception

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

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
        "scrapy-zyte-api/sessions/pools/example.com/init/param-error": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_session_config_pool_caching(mockserver):
    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        def __init__(self, crawler):
            super().__init__(crawler)
            self.pools = deque(("example.com",))

        def pool(self, request: Request):
            # The following code would fail on the second call, which never
            # happens due to pool caching.
            return self.pools.popleft()

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
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
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }
    assert crawler.spider.close_reason == "finished"

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_session_config_pool_error(mockserver):
    # NOTE: This error should only happen during the initial process_request
    # call. By the time the code reaches process_response, the cached pool
    # value for that request is reused, so there is no new call to
    # SessionConfig.pool that could fail during process_response only.

    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):

        def pool(self, request: Request):
            raise Exception

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
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
    assert session_stats == {}
    assert crawler.spider.close_reason == "pool_error"

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_session_config_no_web_poet(mockserver):
    """If web-poet is not installed, @session_config raises a RuntimeError."""
    try:
        import web_poet  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("Test only relevant when web-poet is not installed.")

    with pytest.raises(RuntimeError):

        @session_config(["example.com"])
        class CustomSessionConfig(SessionConfig):
            pass


@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
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
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-fail.example/init/check-failed": 1,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-alternative.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-fail.example/init/failed": 1,
    }


@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://postal-code-10001.example",
            "https://postal-code-10001-alternative.example",
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
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/use/check-passed": 2,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]


@ensureDeferred
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
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://postal-code-10001.example", "https://a.example"]

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
        "scrapy-zyte-api/sessions/pools/postal-code-10001.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/a.example/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/a.example/use/check-passed": 1,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_session_refresh(mockserver):
    """If a response does not pass a session validity check, the session is
    discarded, and the request is retried with a different session."""

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


@ensureDeferred
async def test_session_refresh_concurrent(mockserver):
    """When more than 1 request is using the same session concurrently, it can
    happen that more than 1 response triggers a session refresh. In those
    cases, the same session should be refreshed only once, not once per
    response triggering a refresh."""
    settings = {
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
        "ZYTE_API_SESSION_MAX_ERRORS": 1,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com/"]

        def parse(self, response):
            for n in range(2):
                yield Request(f"https://example.com/{n}?temporary-download-error")

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/failed": 2,
    }


@ensureDeferred
async def test_cookies(mockserver):
    class Tracker:
        def __init__(self):
            self.cookies = []

        def track(self, request: Request, spider: Spider):
            cookie = request.headers.get(b"Cookie", None)
            self.cookies.append(cookie)

    tracker = Tracker()

    settings = {
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_TRANSPARENT_MODE": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request(
                "https://example.com",
                cookies={"a": "b"},
                meta={"zyte_api_session_enabled": False},
            )

        def parse(self, response):
            yield Request(
                "https://example.com/2",
                meta={"zyte_api_session_enabled": False},
                callback=self.parse2,
            )

        def parse2(self, response):
            yield Request(
                "https://example.com/3",
                callback=self.parse3,
            )

        def parse3(self, response):
            yield Request(
                "https://example.com/4",
                meta={"dont_merge_cookies": False},
                callback=self.parse4,
            )

        def parse4(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 2,
        "scrapy-zyte-api/sessions/use/disabled": 2,
    }

    assert tracker.cookies == [
        # The 1st request sets cookies and disables session management, so
        # cookies are set.
        b"a=b",
        # The 2nd request disables session management, and gets the cookies set
        # by the previous request in the global cookiejar.
        b"a=b",
        # The 3rd request uses session management, and neither the session init
        # request nor the actual request using the session get cookies.
        None,
        None,
        # The 4th request uses session management but sets dont_merge_cookies
        # to ``False``, so while session init does not use cookies, the actual
        # request using the session gets the cookies.
        None,
        b"a=b",
    ]


@ensureDeferred
async def test_empty_queue(mockserver):
    """After a pool is full, there might be a situation when the middleware
    tries to assign a session to a request but all sessions of the pool are
    pending creation or a refresh. In those cases, the assign process should
    wait until a session becomes available in the queue."""
    settings = {
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        # We send 2 requests in parallel, so only the first one gets a session
        # created on demand, and the other one is forced to wait until that
        # session is initialized.
        start_urls = ["https://example.com/1", "https://example.com/2"]

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
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 2,
    }


@ensureDeferred
async def test_empty_queue_limit(mockserver):
    settings = {
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS": 1,
        "ZYTE_API_SESSION_QUEUE_WAIT_TIME": 0,
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com/1", "https://example.com/2"]

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
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }


class SessionIDRemovingDownloaderMiddleware:

    def process_exception(
        self, request: Request, exception: Exception, spider: Spider
    ) -> Union[Request, None]:
        if not isinstance(exception, RequestError) or request.meta.get(
            "_is_session_init_request", False
        ):
            return None

        del request.meta["zyte_api_automap"]["session"]
        del request.meta["zyte_api_provider"]["session"]
        return None


@ensureDeferred
async def test_missing_session_id(mockserver, caplog):
    """If a session ID is missing from a request that should have had it
    assigned, a warning is logged about it."""

    settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
            "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
            "tests.test_sessions.SessionIDRemovingDownloaderMiddleware": 675,
        },
        "RETRY_TIMES": 0,
        "ZYTE_API_RETRY_POLICY": "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY",
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_PARAMS": {"url": "https://example.com"},
        "ZYTE_API_SESSION_POOL_SIZE": 1,
        "ZYTE_API_TRANSPARENT_MODE": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://temporary-download-error.example"]

        def parse(self, response):
            pass

    caplog.clear()
    caplog.set_level("WARNING")
    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/temporary-download-error.example/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/temporary-download-error.example/use/failed": 1,
    }
    assert "had no session ID assigned, unexpectedly" in caplog.text


@pytest.mark.parametrize(
    ("settings", "meta", "meta_key"),
    (
        (
            {},
            {},
            "zyte_api",
        ),
        (
            {},
            {"zyte_api": {}},
            "zyte_api",
        ),
        (
            {},
            {"zyte_api": {"httpResponseBody": True}},
            "zyte_api",
        ),
        (
            {},
            {"zyte_api_automap": True},
            "zyte_api_automap",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {},
            "zyte_api_automap",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {"zyte_api_automap": False},
            "zyte_api",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {"zyte_api_automap": {}},
            "zyte_api_automap",
        ),
        (
            {"ZYTE_API_TRANSPARENT_MODE": True},
            {"zyte_api_automap": True},
            "zyte_api_automap",
        ),
    ),
)
@ensureDeferred
async def test_assign_meta_key(settings, meta, meta_key, mockserver):
    """Session ID is set in the zyte_api_provider meta key always, and in
    either zyte_api or zyte_api_automap depending on some settings and meta
    keys."""

    class Tracker:
        def __init__(self):
            self.meta: Dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.meta = deepcopy(request.meta)

    tracker = Tracker()

    settings = {
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        **settings,
    }

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request(
                "https://example.com",
                meta=meta,
            )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }

    assert (
        tracker.meta["zyte_api_provider"]["session"]
        == tracker.meta[meta_key]["session"]
    )
    other_meta_key = "zyte_api" if meta_key != "zyte_api" else "zyte_api_automap"
    assert tracker.meta.get(other_meta_key, False) is False


@ensureDeferred
async def test_provider(mockserver):
    pytest.importorskip("scrapy_poet")

    from scrapy_poet import DummyResponse
    from zyte_common_items import Product

    class Tracker:
        def __init__(self):
            self.query: Dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.query = request.meta["zyte_api"]

    tracker = Tracker()

    settings = {
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"

        def start_requests(self):
            yield Request("https://example.com", callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }
    assert "product" in tracker.query


class ExceptionRaisingDownloaderMiddleware:

    async def process_request(self, request: Request, spider: Spider) -> None:
        if request.meta.get("_is_session_init_request", False):
            return
        raise spider.exception  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("exception", "stat", "reason"),
    (
        (
            mock_request_error(
                status=422, response_content=b'{"type": "/problem/session-expired"}'
            ),
            "expired",
            "session_expired",
        ),
        (
            mock_request_error(status=520),
            "failed",
            "download_error",
        ),
        (
            mock_request_error(status=521),
            "failed",
            "download_error",
        ),
        (
            mock_request_error(status=500),
            None,
            None,
        ),
        (
            ServerConnectionError(),
            None,
            None,
        ),
        (
            RuntimeError(),
            None,
            None,
        ),
    ),
)
@ensureDeferred
async def test_exceptions(exception, stat, reason, mockserver, caplog):
    settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
            "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
            "tests.test_sessions.ExceptionRaisingDownloaderMiddleware": 675,
        },
        "RETRY_TIMES": 0,
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_TRANSPARENT_MODE": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.exception = exception

        def parse(self, response):
            pass

    caplog.clear()
    caplog.set_level("ERROR")
    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await crawler.crawl()

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    if stat is not None:
        assert session_stats == {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 2,
            f"scrapy-zyte-api/sessions/pools/example.com/use/{stat}": 1,
        }
    else:
        assert session_stats == {
            "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        }
    if reason is not None:
        assert reason in caplog.text


@pytest.mark.parametrize(
    ("meta", "expected"),
    (
        ({}, False),
        ({SESSION_INIT_META_KEY: False}, False),
        ({SESSION_INIT_META_KEY: True}, True),
    ),
)
def test_is_session_init_request(meta, expected):
    actual = is_session_init_request(Request("https://example.com", meta=meta))
    assert expected == actual
