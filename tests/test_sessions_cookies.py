from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider, signals

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@deferred_f_from_coro_f
async def test_cookies(mockserver):
    class Tracker:
        def __init__(self):
            self.cookies = []

        def track(self, request: Request, spider: Spider):
            cookie = request.headers.get(b"Cookie", None)
            self.cookies.append(cookie)

    tracker = Tracker()

    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_TRANSPARENT_MODE": True,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

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
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(
        crawler,
        {
            "/pools/example.com/init/check-passed": 2,
            "/pools/example.com/use/check-passed": 2,
            "/use/disabled": 2,
        },
    )

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
