import logging
from typing import Any, Dict, cast
from unittest import SkipTest

import pytest
from packaging.version import Version
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest
from scrapy.http.response import Response
from scrapy.item import Item
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)
from scrapy_zyte_api.exceptions import ActionError
from scrapy_zyte_api.responses import ZyteAPIResponse

from . import SETTINGS
from .mockserver import DelayedResource, MockServer


class NamedSpider(Spider):
    name = "named"


def request_processor(middleware, request, spider):
    assert middleware.process_request(request, spider) is None


def start_request_processor(middleware, request, spider):
    assert list(middleware.process_start_requests([request], spider)) == [request]


def spider_output_processor(middleware, request, spider):
    response = Response("https://example.com")
    assert list(middleware.process_spider_output(response, [request], spider)) == [
        request
    ]


@pytest.mark.parametrize(
    "mw_cls,processor",
    [
        (ScrapyZyteAPIDownloaderMiddleware, request_processor),
        (ScrapyZyteAPISpiderMiddleware, start_request_processor),
        (ScrapyZyteAPISpiderMiddleware, spider_output_processor),
    ],
)
@ensureDeferred
async def test_autothrottle_handling(mw_cls, processor):
    crawler = get_crawler()
    await crawler.crawl("a")
    spider = crawler.spider

    middleware = create_instance(mw_cls, settings=crawler.settings, crawler=crawler)

    # AutoThrottle does this.
    spider.download_delay = 5

    # No effect on non-Zyte-API requests
    request = Request("https://example.com")
    processor(middleware, request, spider)
    assert "download_slot" not in request.meta
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == spider.download_delay

    # On Zyte API requests, the download slot is changed, and its delay is set
    # to 0.
    request = Request("https://example.com", meta={"zyte_api": {}})
    processor(middleware, request, spider)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == 0

    # Requests that happen to already have the right download slot assigned
    # work the same.
    meta = {"download_slot": "zyte-api@example.com", "zyte_api": True}
    request = Request("https://example.com", meta=meta)
    processor(middleware, request, spider)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == 0

    # The slot delay is set to 0 every time a request for the slot is
    # processed, so even if it gets changed later on somehow, the downloader
    # middleware will reset it to 0 again the next time it processes a request.
    slot.delay = 10
    request = Request("https://example.com", meta={"zyte_api": {}})
    processor(middleware, request, spider)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == 0

    await crawler.stop()


@ensureDeferred
async def test_cookies():
    """Make sure that the downloader middleware does not crash on Zyte API
    requests with cookies."""
    settings = {"ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True}
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl("a")
    spider = crawler.spider
    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )
    request = Request(
        "https://example.com", cookies={"a": "b"}, meta={"zyte_api_automap": True}
    )
    assert middleware.process_request(request, spider) is None


@ensureDeferred
async def test_max_requests(caplog):
    spider_requests = 13
    zapi_max_requests = 5

    with MockServer(DelayedResource) as server:

        class TestSpider(Spider):
            name = "test_spider"

            def start_requests(self):
                for i in range(spider_requests):
                    meta = {"zyte_api": {"browserHtml": True}}

                    # Alternating requests between ZAPI and non-ZAPI tests if
                    # ZYTE_API_MAX_REQUESTS solely limits ZAPI Requests.

                    if i % 2:
                        yield Request(
                            "https://example.com", meta=meta, dont_filter=True
                        )
                    else:
                        yield Request("https://example.com", dont_filter=True)

            def parse(self, response):
                yield Item()

        settings = {
            "DOWNLOADER_MIDDLEWARES": {
                "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 1000
            },
            "ZYTE_API_MAX_REQUESTS": zapi_max_requests,
            "ZYTE_API_URL": server.urljoin("/"),
            **SETTINGS,
        }

        crawler = get_crawler(TestSpider, settings_dict=settings)
        with caplog.at_level("INFO"):
            await crawler.crawl()

    assert (
        f"Maximum Zyte API requests for this crawl is set at {zapi_max_requests}"
        in caplog.text
    )
    assert crawler.stats.get_value("scrapy-zyte-api/success") <= zapi_max_requests
    assert crawler.stats.get_value("scrapy-zyte-api/processed") == zapi_max_requests
    assert crawler.stats.get_value("item_scraped_count") == zapi_max_requests + 6
    assert crawler.stats.get_value("finish_reason") == "closespider_max_zapi_requests"
    assert (
        crawler.stats.get_value(
            "downloader/exception_type_count/scrapy.exceptions.IgnoreRequest"
        )
        > 0
    )


@ensureDeferred
async def test_forbidden_domain_start_url():
    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://forbidden.example"]

        def parse(self, response):
            pass

    settings = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "failed_forbidden_domain"


@ensureDeferred
async def test_forbidden_domain_start_urls():
    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://forbidden.example",
            "https://also-forbidden.example",
            "https://oh.definitely-forbidden.example",
        ]

        def parse(self, response):
            pass

    settings = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "failed_forbidden_domain"


@ensureDeferred
async def test_some_forbidden_domain_start_url():
    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://forbidden.example",
            "https://allowed.example",
        ]

        def parse(self, response):
            pass

    settings = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "finished"


@ensureDeferred
async def test_follow_up_forbidden_domain_url():
    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://allowed.example",
        ]

        def parse(self, response):
            yield response.follow("https://forbidden.example")

    settings = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "finished"


@ensureDeferred
async def test_forbidden_domain_with_partial_start_request_consumption():
    """With concurrency lower than the number of start requests + 1, the code
    path followed changes, because ``_total_start_request_count`` is not set
    in the downloader middleware until *after* some start requests have been
    processed."""

    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://forbidden.example",
        ]

        def parse(self, response):
            yield response.follow("https://forbidden.example")

    settings = {
        "CONCURRENT_REQUESTS": 1,
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "failed_forbidden_domain"


@ensureDeferred
async def test_spm_conflict_smartproxy():
    try:
        import scrapy_zyte_smartproxy  # noqa: F401
    except ImportError:
        raise SkipTest("scrapy-zyte-smartproxy missing")

    for setting, attribute, conflict in (
        (None, None, False),
        (None, False, False),
        (None, True, True),
        (False, None, False),
        (False, False, False),
        (False, True, True),
        (True, None, True),
        (True, False, False),
        (True, True, True),
    ):

        class SPMSpider(Spider):
            name = "spm_spider"

        if attribute is not None:
            SPMSpider.zyte_smartproxy_enabled = attribute

        settings = {
            "ZYTE_API_TRANSPARENT_MODE": True,
            "ZYTE_SMARTPROXY_APIKEY": "foo",
            **SETTINGS,
        }
        mws = dict(cast(Dict[Any, int], settings["DOWNLOADER_MIDDLEWARES"]))
        mws["scrapy_zyte_smartproxy.ZyteSmartProxyMiddleware"] = 610
        settings["DOWNLOADER_MIDDLEWARES"] = mws

        if setting is not None:
            settings["ZYTE_SMARTPROXY_ENABLED"] = setting

        crawler = get_crawler(SPMSpider, settings_dict=settings)
        await crawler.crawl()
        expected = "plugin_conflict" if conflict else "finished"
        assert crawler.stats.get_value("finish_reason") == expected, (
            setting,
            attribute,
            conflict,
        )


@ensureDeferred
async def test_spm_conflict_crawlera():
    try:
        import scrapy_crawlera  # noqa: F401
    except ImportError:
        raise SkipTest("scrapy-crawlera missing")
    else:
        SCRAPY_CRAWLERA_VERSION = Version(scrapy_crawlera.__version__)

    for setting, attribute, conflict in (
        (None, None, False),
        (None, False, False),
        (None, True, True),
        (False, None, False),
        (False, False, False),
        (False, True, True),
        (True, None, True),
        # https://github.com/scrapy-plugins/scrapy-zyte-smartproxy/commit/49ebedd8b1d48cf2667db73f18da3e2c2c7fbfa7
        (True, False, SCRAPY_CRAWLERA_VERSION < Version("1.7")),
        (True, True, True),
    ):

        class CrawleraSpider(Spider):
            name = "crawlera_spider"

        if attribute is not None:
            CrawleraSpider.crawlera_enabled = attribute

        settings = {
            "ZYTE_API_TRANSPARENT_MODE": True,
            "CRAWLERA_APIKEY": "foo",
            **SETTINGS,
        }
        mws = dict(cast(Dict[Any, int], settings["DOWNLOADER_MIDDLEWARES"]))
        mws["scrapy_crawlera.CrawleraMiddleware"] = 610
        settings["DOWNLOADER_MIDDLEWARES"] = mws

        if setting is not None:
            settings["CRAWLERA_ENABLED"] = setting

        crawler = get_crawler(CrawleraSpider, settings_dict=settings)
        await crawler.crawl()
        expected = "plugin_conflict" if conflict else "finished"
        assert crawler.stats.get_value("finish_reason") == expected, (
            setting,
            attribute,
            conflict,
        )


@pytest.mark.parametrize(
    "settings,meta,enabled",
    [
        # ZYTE_API_ACTION_ERROR_RETRY_ENABLED enables, RETRY_ENABLED has no
        # effect.
        *(
            (
                {
                    "RETRY_ENABLED": scrapy,
                    "ZYTE_API_ACTION_ERROR_RETRY_ENABLED": zyte_api,
                },
                {},
                zyte_api,
            )
            for zyte_api in (True, False)
            for scrapy in (True, False)
        ),
        *(
            (
                {
                    "RETRY_ENABLED": scrapy,
                },
                {},
                True,
            )
            for scrapy in (True, False)
        ),
        # dont_retry=True overrides.
        *(
            (
                {"ZYTE_API_ACTION_ERROR_RETRY_ENABLED": zyte_api},
                {"dont_retry": dont_retry},
                zyte_api and not dont_retry,
            )
            for zyte_api in (True, False)
            for dont_retry in (True, False)
        ),
    ],
)
@ensureDeferred
async def test_action_error_retry_enabled(settings, meta, enabled):
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )

    request = Request("https://example.com", meta=meta)
    raw_api_response = {"url": request.url, "actions": [{"error": "foo"}]}
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)
    result = middleware.process_response(request, response, crawler.spider)
    if enabled:
        assert isinstance(result, Request)
        assert result.meta["retry_times"] == 1
    else:
        assert result is response

    await crawler.stop()


@pytest.mark.parametrize(
    "settings,meta,max_retries",
    [
        (
            {"RETRY_TIMES": 1},
            {},
            1,
        ),
        (
            {},
            {"max_retry_times": 1},
            1,
        ),
        (
            {"RETRY_TIMES": 1},
            {"max_retry_times": 2},
            2,
        ),
        (
            {"RETRY_TIMES": 2},
            {"max_retry_times": 1},
            1,
        ),
    ],
)
@ensureDeferred
async def test_action_error_retry_times(settings, meta, max_retries):
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )

    request = Request(
        "https://example.com", meta={**meta, "retry_times": max_retries - 1}
    )
    raw_api_response = {"url": request.url, "actions": [{"error": "foo"}]}
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)

    request2 = middleware.process_response(request, response, crawler.spider)
    assert isinstance(request2, Request)
    assert request2.meta["retry_times"] == max_retries

    result = middleware.process_response(request2, response, crawler.spider)
    assert result is response

    await crawler.stop()


@pytest.mark.parametrize(
    "settings,meta,priority",
    [
        (
            {"RETRY_PRIORITY_ADJUST": 1},
            {},
            1,
        ),
        (
            {},
            {"priority_adjust": 1},
            1,
        ),
        (
            {"RETRY_PRIORITY_ADJUST": 1},
            {"priority_adjust": 2},
            2,
        ),
        (
            {"RETRY_PRIORITY_ADJUST": 2},
            {"priority_adjust": 1},
            1,
        ),
    ],
)
@ensureDeferred
async def test_action_error_retry_priority_adjust(settings, meta, priority):
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )

    request = Request("https://example.com", meta=meta)
    raw_api_response = {"url": request.url, "actions": [{"error": "foo"}]}
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)

    request2 = middleware.process_response(request, response, crawler.spider)
    assert isinstance(request2, Request)
    assert request2.meta["retry_times"] == 1
    assert request2.priority == priority

    await crawler.stop()


@pytest.mark.parametrize(
    "settings,expected,setup_errors",
    [
        (
            {},
            Response,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "pass"},
            Response,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "ignore"},
            IgnoreRequest,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "err"},
            ActionError,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "foo"},
            Response,
            [
                (
                    "Setting ZYTE_API_ACTION_ERROR_HANDLING got an unexpected "
                    "value: 'foo'. Falling back to 'pass'."
                )
            ],
        ),
    ],
)
@ensureDeferred
async def test_action_error_handling_no_retries(
    settings, expected, setup_errors, caplog
):
    settings["ZYTE_API_ACTION_ERROR_RETRY_ENABLED"] = False
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )
    if setup_errors:
        assert caplog.record_tuples == [
            ("scrapy_zyte_api._middlewares", logging.ERROR, error)
            for error in setup_errors
        ]
    else:
        assert not caplog.records

    request = Request("https://example.com")
    raw_api_response = {"url": request.url, "actions": [{"error": "foo"}]}
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)

    try:
        result = middleware.process_response(request, response, crawler.spider)
    except (ActionError, IgnoreRequest) as e:
        result = e
    assert isinstance(result, expected)

    await crawler.stop()


@pytest.mark.parametrize(
    "settings,expected,setup_errors",
    [
        (
            {},
            Response,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "pass"},
            Response,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "ignore"},
            IgnoreRequest,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "err"},
            ActionError,
            [],
        ),
        (
            {"ZYTE_API_ACTION_ERROR_HANDLING": "foo"},
            Response,
            [
                (
                    "Setting ZYTE_API_ACTION_ERROR_HANDLING got an unexpected "
                    "value: 'foo'. Falling back to 'pass'."
                )
            ],
        ),
    ],
)
@ensureDeferred
async def test_action_error_handling_retries(settings, expected, setup_errors, caplog):
    settings["RETRY_TIMES"] = 1
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )
    if setup_errors:
        assert caplog.record_tuples == [
            ("scrapy_zyte_api._middlewares", logging.ERROR, error)
            for error in setup_errors
        ]
    else:
        assert not caplog.records

    request = Request("https://example.com")
    raw_api_response = {"url": request.url, "actions": [{"error": "foo"}]}
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)

    request2 = middleware.process_response(request, response, crawler.spider)
    assert isinstance(request2, Request)
    assert request2.meta["retry_times"] == 1

    try:
        result = middleware.process_response(request2, response, crawler.spider)
    except (ActionError, IgnoreRequest) as e:
        result = e
    assert isinstance(result, expected)

    await crawler.stop()


@ensureDeferred
async def test_process_response_non_zyte_api():
    crawler = get_crawler()
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )

    request = Request("https://example.com")
    response = Response(request.url)
    result = middleware.process_response(request, response, crawler.spider)
    assert result is response

    await crawler.stop()


@ensureDeferred
async def test_process_response_no_action_error():
    crawler = get_crawler()
    await crawler.crawl()

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )

    request = Request("https://example.com")
    raw_api_response = {"url": request.url, "actions": [{"action": "foo"}]}
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)

    result = middleware.process_response(request, response, crawler.spider)
    assert result is response

    await crawler.stop()
