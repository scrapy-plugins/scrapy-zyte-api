from typing import Dict, Tuple, Union

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider
from scrapy.exceptions import CloseSpider
from scrapy.http import Response
from scrapy.utils.misc import load_object

from scrapy_zyte_api import SessionConfig, session_config
from scrapy_zyte_api._session import SESSION_INIT_META_KEY, session_config_registry
from scrapy_zyte_api.utils import (
    _RAW_CLASS_SETTING_SUPPORT,
    maybe_deferred_to_future,
)

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


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

CHECKER_TESTS: Tuple[
    Tuple[
        Union[type, str],
        str,
        Dict[str, Union[Tuple[int, int], Dict[str, int]]],
    ],
    ...,
] = (
    (TrueChecker, "finished", {"example.com": (1, 1)}),
    (FalseChecker, "bad_session_inits", {"example.com": {"init/check-failed": 1}}),
    (
        FalseUseChecker,
        "finished",
        {"example.com": {"init/check-passed": 2, "use/check-failed": 1}},
    ),
    (CloseSpiderChecker, "closed_by_checker", {}),
    (
        CloseSpiderUseChecker,
        "closed_by_checker",
        {"example.com": {"init/check-passed": 1}},
    ),
    (
        UnexpectedExceptionChecker,
        "bad_session_inits",
        {"example.com": {"init/check-error": 1}},
    ),
    (
        UnexpectedExceptionUseChecker,
        "finished",
        {"example.com": {"init/check-passed": 2, "use/check-error": 1}},
    ),
    (TrueCrawlerChecker, "finished", {"example.com": (1, 1)}),
    (
        FalseCrawlerChecker,
        "bad_session_inits",
        {"example.com": {"init/check-failed": 1}},
    ),
    (
        OnlyPassFirstInitChecker,
        "bad_session_inits",
        {
            "example.com": {
                "init/check-passed": 1,
                "init/check-failed": 1,
                "use/check-failed": 1,
            }
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
@deferred_f_from_coro_f
async def test_checker(checker, close_reason, stats, mockserver):
    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_CHECKER": checker,
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
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.spider.close_reason == close_reason
    assert_session_stats(crawler, stats)


class CloseSpiderURLChecker:
    def check(self, response: Response, request: Request) -> bool:
        if "fail" in request.url:
            raise CloseSpider("closed_by_checker")
        return True


@deferred_f_from_coro_f
async def test_checker_close_spider_use(mockserver):
    """A checker can raise CloseSpider not only during session initialization,
    but also during session use."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_SESSION_CHECKER": "tests.test_sessions_check_custom.CloseSpiderURLChecker",
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
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.spider.close_reason == "closed_by_checker"
    assert_session_stats(crawler, {"example.com": {"init/check-passed": 1}})


@deferred_f_from_coro_f
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
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
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
                        "zyte_api_automap": params,
                        "zyte_api_session_params": params,
                        "zyte_api_session_location": {"postalCode": "10001"},
                        "zyte_api_session_foo": "bar",
                    },
                )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com[0]": (1, 1)})

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]
