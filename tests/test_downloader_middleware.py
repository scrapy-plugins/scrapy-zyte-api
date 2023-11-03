from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.item import Item
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import ScrapyZyteAPIDownloaderMiddleware

from . import SETTINGS
from .mockserver import DelayedResource, MockServer


@ensureDeferred
async def test_autothrottle_handling():
    crawler = get_crawler()
    await crawler.crawl("a")
    spider = crawler.spider

    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )

    # AutoThrottle does this.
    spider.download_delay = 5

    # No effect on non-Zyte-API requests
    request = Request("https://example.com")
    assert middleware.process_request(request, spider) is None
    assert "download_slot" not in request.meta
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == spider.download_delay

    # On Zyte API requests, the download slot is changed, and its delay is set
    # to 0.
    request = Request("https://example.com", meta={"zyte_api": {}})
    assert middleware.process_request(request, spider) is None
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == 0

    # Requests that happen to already have the right download slot assigned
    # work the same.
    meta = {"download_slot": "zyte-api@example.com", "zyte_api": True}
    request = Request("https://example.com", meta=meta)
    assert middleware.process_request(request, spider) is None
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == 0

    # The slot delay is set to 0 every time a request for the slot is
    # processed, so even if it gets changed later on somehow, the downloader
    # middleware will reset it to 0 again the next time it processes a request.
    slot.delay = 10
    request = Request("https://example.com", meta={"zyte_api": {}})
    assert middleware.process_request(request, spider) is None
    assert request.meta["download_slot"] == "zyte-api@example.com"
    _, slot = crawler.engine.downloader._get_slot(request, spider)
    assert slot.delay == 0

    await crawler.stop()


@ensureDeferred
async def test_cookies():
    """Make sure that the downloader middleware does not crash on Zyte API
    requests with cookies."""
    crawler = get_crawler()
    await crawler.crawl("a")
    spider = crawler.spider
    middleware = create_instance(
        ScrapyZyteAPIDownloaderMiddleware, settings=crawler.settings, crawler=crawler
    )
    request = Request(
        "https://example.com", cookies={"a": "b"}, meta={"zyte_api_automap": True}
    )
    assert middleware.process_request(request, spider) is None
    assert request.meta["download_slot"] == "zyte-api@example.com"


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
