from typing import Any, Dict, cast
from unittest import SkipTest

import pytest
from packaging.version import Version
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.http.response import Response
from scrapy.item import Item
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)

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
@ensureDeferred
async def test_preserve_delay(mw_cls, processor, settings, preserve):
    crawler = get_crawler(settings_dict=settings)
    await crawler.crawl("a")
    assert crawler.engine
    assert crawler.spider
    spider = crawler.spider

    middleware = create_instance(mw_cls, settings=crawler.settings, crawler=crawler)

    # AutoThrottle does this.
    spider.download_delay = 5  # type: ignore[attr-defined]

    # No effect on non-Zyte-API requests
    request = Request("https://example.com")
    processor(middleware, request, spider)
    assert "download_slot" not in request.meta
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == spider.download_delay  # type: ignore[attr-defined]

    # On Zyte API requests, the download slot is changed, and its delay may be
    # set to 0 depending on settings.
    request = Request("https://example.com", meta={"zyte_api": {}})
    processor(middleware, request, spider)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == (5 if preserve else 0)

    # Requests that happen to already have the right download slot assigned
    # work the same.
    meta = {"download_slot": "zyte-api@example.com", "zyte_api": True}
    request = Request("https://example.com", meta=meta)
    processor(middleware, request, spider)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == (5 if preserve else 0)

    # The slot delay is taken into account every time a request for the slot is
    # processed, so even if it gets changed later on somehow, the downloader
    # middleware may reset it to 0 again the next time it processes a request
    # depending on settings.
    slot.delay = 10
    request = Request("https://example.com", meta={"zyte_api": {}})
    processor(middleware, request, spider)
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == (10 if preserve else 0)

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
            await crawler.crawl()

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


@ensureDeferred
async def test_max_requests_race_condition(caplog):
    spider_requests = 8
    zapi_max_requests = 1

    with MockServer(DelayedResource) as server:

        class TestSpider(Spider):
            name = "test_spider"

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
            await crawler.crawl()

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

    assert crawler.stats
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

    assert crawler.stats
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

    assert crawler.stats
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

    assert crawler.stats
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
@ensureDeferred
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
    await crawler.crawl()
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
@ensureDeferred
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
    await crawler.crawl()
    expected = "plugin_conflict" if conflict else "finished"
    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == expected, (
        setting,
        attribute,
        conflict,
    )
