from pytest_twisted import ensureDeferred
from scrapy import Request
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import ScrapyZyteAPIDownloaderMiddleware


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
    assert request.meta["download_slot"] == "zyte-api@example.com"
