import logging

import pytest

pytest.importorskip("scrapy_poet")

from typing import Any

import attrs
from scrapy import Request, Spider, signals
from scrapy_poet import DummyResponse
from web_poet import (
    BrowserResponse,
    HttpClient,
    ItemPage,
    default_registry,
    handle_urls,
)
from web_poet.exceptions import Retry
from zyte_common_items import Product

from scrapy_zyte_api import NoSession, ScrapyZyteAPISessionDownloaderMiddleware, Session
from scrapy_zyte_api.utils import _GET_COMPONENT_SUPPORT, maybe_deferred_to_future

from . import SESSION_SETTINGS, deferred_f_from_coro_f, get_crawler
from .helpers import assert_session_stats


@deferred_f_from_coro_f
async def test_provider(mockserver):
    class Tracker:
        def __init__(self):
            self.query: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            self.query = request.meta["zyte_api"]

    tracker = Tracker()

    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com", callback=self.parse)  # type: ignore[arg-type]

        def parse(self, response: DummyResponse, product: Product):  # type: ignore[override]
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": (1, 1)})
    assert "product" in tracker.query


@attrs.define
class MyItem:
    foo: str


DISCARD_SETTINGS = {
    **SESSION_SETTINGS,
    "RETRY_TIMES": 1,
    "ZYTE_API_SESSION_POOL_SIZE": 1,
    # With a single session per pool, discarding a session empties the session
    # rotation queue, so retries must wait for the replacement session.
    "ZYTE_API_SESSION_QUEUE_WAIT_TIME": 0.1,
}


@pytest.mark.skipif(
    not _GET_COMPONENT_SUPPORT,
    reason="Discarding sessions from user code requires Scrapy 2.12 or higher",
)
@deferred_f_from_coro_f
async def test_discard_session_middleware_method(mockserver):
    """discard_session() also discards the sessions of the Zyte API requests
    that the provider sent to build the page inputs of a request."""

    @attrs.define
    class MyPage(ItemPage[MyItem]):
        response: BrowserResponse

        async def to_item(self):
            return MyItem(foo="bar")

    handle_urls("example.com")(MyPage)

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        async def parse(self, response: DummyResponse, page: MyPage):  # type: ignore[override]
            middleware = self.crawler.get_downloader_middleware(
                ScrapyZyteAPISessionDownloaderMiddleware
            )
            assert middleware is not None
            middleware.discard_session(response)

    try:
        crawler = await get_crawler(
            {**DISCARD_SETTINGS, "ZYTE_API_URL": mockserver.urljoin("/")},
            spider_cls=TestSpider,
            setup_engine=False,
        )
        await maybe_deferred_to_future(crawler.crawl())
    finally:
        default_registry.__init__()  # type: ignore[misc]

    assert_session_stats(
        crawler,
        {
            "example.com": {
                "init/check-passed": 2,
                "use/check-passed": 1,
                "use/discarded": 1,
            }
        },
    )


@pytest.mark.skipif(
    not _GET_COMPONENT_SUPPORT,
    reason="Discarding sessions from user code requires Scrapy 2.12 or higher",
)
@deferred_f_from_coro_f
async def test_discard_session_additional_requests(mockserver):
    """Sessions used for the additional requests of a page object are not
    discarded when discarding the session of the source request."""
    calls = []

    @attrs.define
    class MyPage(ItemPage[MyItem]):
        response: BrowserResponse
        http: HttpClient
        session: Session

        async def to_item(self):
            await self.http.get("https://additional.example")
            calls.append(1)
            if len(calls) == 1:
                self.session.discard()
                raise Retry
            return MyItem(foo="bar")

    handle_urls("example.com")(MyPage)

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        async def parse(self, response: DummyResponse, page: MyPage):  # type: ignore[override]
            return await page.to_item()

    try:
        crawler = await get_crawler(
            {**DISCARD_SETTINGS, "ZYTE_API_URL": mockserver.urljoin("/")},
            spider_cls=TestSpider,
            setup_engine=False,
        )
        await maybe_deferred_to_future(crawler.crawl())
    finally:
        default_registry.__init__()  # type: ignore[misc]

    assert_session_stats(
        crawler,
        {
            # Only the session of the Zyte API request that the provider sent
            # is discarded and replaced.
            "example.com": {
                "init/check-passed": 2,
                "use/check-passed": 2,
                "use/discarded": 1,
            },
            # The session of the additional request is left alone.
            "additional.example": {
                "init/check-passed": 1,
                "use/check-passed": 2,
            },
        },
    )
    assert crawler.stats.get_value("item_scraped_count") == 1


@pytest.mark.skipif(
    not _GET_COMPONENT_SUPPORT,
    reason="Discarding sessions from user code requires Scrapy 2.12 or higher",
)
@deferred_f_from_coro_f
async def test_session_input(mockserver):
    """A page object can discard the session used to build its page inputs
    through the Session page input, and get its request retried by raising
    web_poet.exceptions.Retry, even when to_item() is called by scrapy-poet
    while building the dependencies of a callback."""
    calls = []

    @attrs.define
    class MyPage(ItemPage[MyItem]):
        response: BrowserResponse
        session: Session

        async def to_item(self):
            calls.append(1)
            if len(calls) == 1:
                self.session.discard()
                raise Retry
            return MyItem(foo="bar")

    handle_urls("example.com")(MyPage)

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        async def parse(self, response: DummyResponse, item: MyItem):  # type: ignore[override]
            return item

    try:
        crawler = await get_crawler(
            {**DISCARD_SETTINGS, "ZYTE_API_URL": mockserver.urljoin("/")},
            spider_cls=TestSpider,
            setup_engine=False,
        )
        await maybe_deferred_to_future(crawler.crawl())
    finally:
        default_registry.__init__()  # type: ignore[misc]

    assert_session_stats(
        crawler,
        {
            "example.com": {
                "init/check-passed": 2,
                "use/check-passed": 2,
                "use/discarded": 1,
            }
        },
    )
    assert crawler.stats.get_value("retry/reason_count/page_object_retry") == 1
    assert crawler.stats.get_value("item_scraped_count") == 1


@pytest.mark.skipif(
    not _GET_COMPONENT_SUPPORT,
    reason="Discarding sessions from user code requires Scrapy 2.12 or higher",
)
@deferred_f_from_coro_f
async def test_session_input_no_session(mockserver):
    """Session.discard() raises NoSession if session management is not enabled
    for the requests of the page object."""
    exceptions = []

    @attrs.define
    class MyPage(ItemPage[MyItem]):
        response: BrowserResponse
        session: Session

        async def to_item(self):
            try:
                self.session.discard()
            except NoSession as exception:
                exceptions.append(exception)
            return MyItem(foo="bar")

    handle_urls("example.com")(MyPage)

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        async def parse(self, response: DummyResponse, item: MyItem):  # type: ignore[override]
            return item

    try:
        crawler = await get_crawler(
            {"ZYTE_API_URL": mockserver.urljoin("/")},
            spider_cls=TestSpider,
            setup_engine=False,
        )
        await maybe_deferred_to_future(crawler.crawl())
    finally:
        default_registry.__init__()  # type: ignore[misc]

    assert len(exceptions) == 1
    assert "no plugin-managed session was used" in str(exceptions[0])
    assert crawler.stats.get_value("item_scraped_count") == 1


def test_session_input_detached(caplog):
    """A Session page input deserialized from a web-poet test fixture has no
    session to discard, so discard() does nothing."""
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        Session().discard()
    assert "not associated to a request" in caplog.text
