from pytest_twisted import ensureDeferred
from scrapy import Spider
from scrapy.utils.test import get_crawler

from . import SETTINGS
from .mockserver import MockServer


@ensureDeferred
async def test_single_forbidden():
    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://forbidden.example"]

        def parse(self, response):
            pass

    settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 1000,
            "scrapy_zyte_api.ForbiddenDomainDownloaderMiddleware": 1100,
        },
        "SPIDER_MIDDLEWARES": {
            "scrapy_zyte_api.ForbiddenDomainSpiderMiddleware": 100,
        },
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "failed-forbidden-domain"


@ensureDeferred
async def test_multiple_forbidden():
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
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 1000,
            "scrapy_zyte_api.ForbiddenDomainDownloaderMiddleware": 1100,
        },
        "SPIDER_MIDDLEWARES": {
            "scrapy_zyte_api.ForbiddenDomainSpiderMiddleware": 100,
        },
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "failed-forbidden-domain"


@ensureDeferred
async def test_some_forbidden():
    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://forbidden.example",
            "https://allowed.example",
        ]

        def parse(self, response):
            pass

    settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 1000,
            "scrapy_zyte_api.ForbiddenDomainDownloaderMiddleware": 1100,
        },
        "SPIDER_MIDDLEWARES": {
            "scrapy_zyte_api.ForbiddenDomainSpiderMiddleware": 100,
        },
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats.get_value("finish_reason") == "finished"
