from typing import Any, Dict, cast
from unittest import SkipTest

import pytest
from packaging.version import Version
from scrapy import Request, Spider
from scrapy.http.response import Response
from scrapy.item import Item
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)
from scrapy_zyte_api.utils import (  # type: ignore[attr-defined]
    _GET_SLOT_NEEDS_SPIDER,
    _PROCESS_SPIDER_OUTPUT_ASYNC_SUPPORT,
    _START_REQUESTS_CAN_YIELD_ITEMS,
    _build_from_crawler,
    maybe_deferred_to_future,
    _PROCESS_SPIDER_OUTPUT_REQUIRES_SPIDER,
    _PROCESS_START_REQUIRES_SPIDER,
)

from . import SETTINGS, process_request
from .mockserver import DelayedResource, MockServer


class NamedSpider(Spider):
    name = "named"


async def request_processor(middleware, request: Request):
    assert await process_request(middleware, request) is None


async def aiter(list_):
    for item in list_:
        yield item


async def start_request_processor(middleware, request: Request):
    if hasattr(middleware, "process_start"):
        args = (None,) if _PROCESS_START_REQUIRES_SPIDER else ()
        result = [
            request
            async for request in middleware.process_start(aiter([request]), *args)
        ]
    else:
        result = list(middleware.process_start_requests([request], None))
    assert result == [request]


async def spider_output_processor(middleware, request: Request):
    response = Response("https://example.com")
    args = (None,) if _PROCESS_SPIDER_OUTPUT_REQUIRES_SPIDER else ()
    if _PROCESS_SPIDER_OUTPUT_ASYNC_SUPPORT:
        result = [
            request
            async for request in middleware.process_spider_output_async(
                response, aiter([request]), *args
            )
        ]
    else:
        result = list(middleware.process_spider_output(response, [request], *args))
    assert result == [request]


@pytest.mark.parametrize(
    ["mw_cls", "processor"],
    [
        (ScrapyZyteAPIDownloaderMiddleware, request_processor),
        (ScrapyZyteAPISpiderMiddleware, start_request_processor),
        (ScrapyZyteAPISpiderMiddleware, spider_output_processor),
    ],
)
@pytest.mark.parametrize(
    ["settings", "preserve"],
    [
        ({}, True),
        ({"ZYTE_API_PRESERVE_DELAY": False}, False),
        ({"ZYTE_API_PRESERVE_DELAY": True}, True),
        ({"AUTOTHROTTLE_ENABLED": True}, False),
        ({"AUTOTHROTTLE_ENABLED": True, "ZYTE_API_PRESERVE_DELAY": True}, True),
    ],
)
@deferred_f_from_coro_f
async def test_preserve_delay(mw_cls, processor, settings, preserve):
    crawler = get_crawler(settings_dict=settings)
    await maybe_deferred_to_future(crawler.crawl("a"))
    assert crawler.engine
    assert crawler.spider
    spider = crawler.spider

    middleware = _build_from_crawler(mw_cls, crawler)

    # AutoThrottle does this.
    spider.download_delay = 5  # type: ignore[attr-defined]

    # No effect on non-Zyte-API requests
    request = Request("https://example.com")
    await processor(middleware, request)
    assert "download_slot" not in request.meta
    args = (crawler.spider,) if _GET_SLOT_NEEDS_SPIDER else ()
    _, slot = crawler.engine.downloader._get_slot(request, *args)
    assert slot.delay == spider.download_delay  # type: ignore[attr-defined]

    # On Zyte API requests, the download slot is changed, and its delay may be
    # set to 0 depending on settings.
    request = Request("https://example.com", meta={"zyte_api": {}})
    await processor(middleware, request)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    args = (crawler.spider,) if _GET_SLOT_NEEDS_SPIDER else ()
    _, slot = crawler.engine.downloader._get_slot(request, *args)
    assert slot.delay == (5 if preserve else 0)

    # Requests that happen to already have the right download slot assigned
    # work the same.
    meta = {"download_slot": "zyte-api@example.com", "zyte_api": True}
    request = Request("https://example.com", meta=meta)
    await processor(middleware, request)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    args = (crawler.spider,) if _GET_SLOT_NEEDS_SPIDER else ()
    _, slot = crawler.engine.downloader._get_slot(request, *args)
    assert slot.delay == (5 if preserve else 0)

    # The slot delay is taken into account every time a request for the slot is
    # processed, so even if it gets changed later on somehow, the downloader
    # middleware may reset it to 0 again the next time it processes a request
    # depending on settings.
    slot.delay = 10
    request = Request("https://example.com", meta={"zyte_api": {}})
    await processor(middleware, request)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    args = (crawler.spider,) if _GET_SLOT_NEEDS_SPIDER else ()
    _, slot = crawler.engine.downloader._get_slot(request, *args)
    assert slot.delay == (10 if preserve else 0)

    if hasattr(crawler, "stop_async"):
        await crawler.stop_async()
    else:
        await maybe_deferred_to_future(crawler.stop())


@deferred_f_from_coro_f
async def test_cookies():
    """Make sure that the downloader middleware does not crash on Zyte API
    requests with cookies."""
    settings = {"ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED": True}
    crawler = get_crawler(settings_dict=settings)
    await maybe_deferred_to_future(crawler.crawl("a"))
    middleware = _build_from_crawler(ScrapyZyteAPIDownloaderMiddleware, crawler)
    request = Request(
        "https://example.com", cookies={"a": "b"}, meta={"zyte_api_automap": True}
    )
    assert await process_request(middleware, request) is None


@deferred_f_from_coro_f
async def test_max_requests(caplog):
    spider_requests = 13
    zapi_max_requests = 5

    with MockServer(DelayedResource) as server:

        class TestSpider(Spider):
            name = "test_spider"

            async def start(self):
                for request in self.start_requests():
                    yield request

            def start_requests(self):
                for i in range(spider_requests):
                    meta = {"zyte_api": {"browserHtml": True}}

                    # Alternating requests between ZAPI and non-ZAPI verifies
                    # that ZYTE_API_MAX_REQUESTS solely limits ZAPI requests.

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
                "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633
            },
            "ZYTE_API_MAX_REQUESTS": zapi_max_requests,
            "ZYTE_API_URL": server.urljoin("/"),
            **SETTINGS,
        }

        crawler = get_crawler(TestSpider, settings_dict=settings)
        with caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

    assert (
        f"Maximum Zyte API requests for this crawl is set at {zapi_max_requests}"
        in caplog.text
    )
    assert crawler.stats
    assert crawler.stats.get_value("scrapy-zyte-api/success") == zapi_max_requests
    assert crawler.stats.get_value("scrapy-zyte-api/processed") == zapi_max_requests
    assert crawler.stats.get_value("item_scraped_count") <= zapi_max_requests + 6
    assert crawler.stats.get_value("finish_reason") == "closespider_max_zapi_requests"
    assert (
        crawler.stats.get_value(
            "downloader/exception_type_count/scrapy.exceptions.IgnoreRequest"
        )
        > 0
    )


@deferred_f_from_coro_f
async def test_max_requests_race_condition(caplog):
    spider_requests = 8
    zapi_max_requests = 1

    with MockServer(DelayedResource) as server:

        class TestSpider(Spider):
            name = "test_spider"

            async def start(self):
                for request in self.start_requests():
                    yield request

            def start_requests(self):
                for i in range(spider_requests):
                    meta = {"zyte_api": {"browserHtml": True}}
                    yield Request("https://example.com", meta=meta, dont_filter=True)

            def parse(self, response):
                yield Item()

        settings = {
            "DOWNLOADER_MIDDLEWARES": {
                "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633
            },
            "ZYTE_API_MAX_REQUESTS": zapi_max_requests,
            "ZYTE_API_URL": server.urljoin("/"),
            **SETTINGS,
        }

        crawler = get_crawler(TestSpider, settings_dict=settings)
        with caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

    assert (
        f"Maximum Zyte API requests for this crawl is set at {zapi_max_requests}"
        in caplog.text
    )
    assert crawler.stats
    assert crawler.stats.get_value("scrapy-zyte-api/success") == zapi_max_requests
    assert crawler.stats.get_value("scrapy-zyte-api/processed") == zapi_max_requests
    assert crawler.stats.get_value("item_scraped_count") == zapi_max_requests
    assert crawler.stats.get_value("finish_reason") == "closespider_max_zapi_requests"
    assert (
        crawler.stats.get_value(
            "downloader/exception_type_count/scrapy.exceptions.IgnoreRequest"
        )
        > 0
    )


@deferred_f_from_coro_f
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
        await maybe_deferred_to_future(crawler.crawl())

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "failed_forbidden_domain"


@deferred_f_from_coro_f
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
        await maybe_deferred_to_future(crawler.crawl())

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "failed_forbidden_domain"


@deferred_f_from_coro_f
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
        await maybe_deferred_to_future(crawler.crawl())

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "finished"


@deferred_f_from_coro_f
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
        await maybe_deferred_to_future(crawler.crawl())

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "finished"


@deferred_f_from_coro_f
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
        await maybe_deferred_to_future(crawler.crawl())

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "failed_forbidden_domain"


@pytest.mark.parametrize(
    "setting,attribute,conflict",
    [
        (None, None, False),
        (None, False, False),
        (None, True, True),
        (False, None, False),
        (False, False, False),
        (False, True, True),
        (True, None, True),
        (True, False, False),
        (True, True, True),
    ],
)
@deferred_f_from_coro_f
async def test_spm_conflict_smartproxy(setting, attribute, conflict):
    try:
        import scrapy_zyte_smartproxy  # noqa: F401
    except ImportError:
        raise SkipTest("scrapy-zyte-smartproxy missing")

    class SPMSpider(Spider):
        name = "spm_spider"
        start_urls = ["data:,"]

    if attribute is not None:
        SPMSpider.zyte_smartproxy_enabled = attribute  # type: ignore[attr-defined]

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
    await maybe_deferred_to_future(crawler.crawl())
    expected = "plugin_conflict" if conflict else "finished"
    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == expected


try:
    import scrapy_crawlera  # noqa: F401
except ImportError:
    scrapy_crawlera = None
    SCRAPY_CRAWLERA_VERSION = Version("1.2.3")
else:
    SCRAPY_CRAWLERA_VERSION = Version(scrapy_crawlera.__version__)


@pytest.mark.parametrize(
    "setting,attribute,conflict",
    [
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
    ],
)
@deferred_f_from_coro_f
async def test_spm_conflict_crawlera(setting, attribute, conflict):
    if scrapy_crawlera is None:
        raise SkipTest("scrapy-crawlera missing")

    class CrawleraSpider(Spider):
        name = "crawlera_spider"
        start_urls = ["data:,"]

    if attribute is not None:
        CrawleraSpider.crawlera_enabled = attribute  # type: ignore[attr-defined]

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
    await maybe_deferred_to_future(crawler.crawl())
    expected = "plugin_conflict" if conflict else "finished"
    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == expected, (
        setting,
        attribute,
        conflict,
    )


@pytest.mark.skipif(not _START_REQUESTS_CAN_YIELD_ITEMS, reason="Scrapy < 2.12")
@deferred_f_from_coro_f
async def test_start_requests_items():
    class TestSpider(Spider):
        name = "test"

        async def start(self):
            yield {"foo": "bar"}

        def start_requests(self):
            yield {"foo": "bar"}

    crawler = get_crawler(TestSpider, settings_dict=SETTINGS)
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.stats is not None
    assert crawler.stats.get_value("finish_reason") == "finished"
    assert "log_count/ERROR" not in crawler.stats.get_stats()
