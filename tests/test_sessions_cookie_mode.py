import logging
from copy import deepcopy
from typing import Any

import pytest
from scrapy import Request, Spider, signals
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.httpobj import urlparse_cached

from scrapy_zyte_api import (
    ScrapyZyteAPISessionDownloaderMiddleware,
    SessionConfig,
    get_request_session_id,
    session_config,
)
from scrapy_zyte_api._session import (
    COOKIE_SESSION_ID_META_KEY,
    _SessionManager,
    session_config_registry,
)
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, UNSET, get_crawler
from .helpers import assert_session_stats

COOKIE_SESSION_SETTINGS = {
    **SESSION_SETTINGS,
    "ZYTE_API_SESSION_COOKIE_MODE": True,
}

_EXPECTED_COOKIES = [
    {"name": "test_cookie", "value": "test_value", "domain": "example.com", "path": "/"}
]

# Cookie returned by the mockserver on use requests (which carry requestCookies).
_EXTRA_COOKIE = {
    "name": "extra_cookie",
    "value": "extra_value",
    "domain": "example.com",
    "path": "/",
}


@pytest.mark.parametrize(
    ("setting", "meta", "outcome"),
    [
        (UNSET, UNSET, False),
        (UNSET, True, True),
        (UNSET, False, False),
        (True, UNSET, True),
        (True, True, True),
        (True, False, False),
        (False, UNSET, False),
        (False, True, True),
        (False, False, False),
    ],
)
@deferred_f_from_coro_f
async def test_cookie_mode_precedence(setting, meta, outcome, mockserver):
    """The zyte_api_session_cookie_mode meta key takes priority over the
    ZYTE_API_SESSION_COOKIE_MODE setting."""
    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }
    if setting is not UNSET:
        settings["ZYTE_API_SESSION_COOKIE_MODE"] = setting

    meta_dict: dict[str, Any] = {}
    if meta is not UNSET:
        meta_dict["zyte_api_session_cookie_mode"] = meta

    class Tracker:
        def __init__(self):
            self.use_meta: dict[str, Any] = {}
            self.init_meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            if request.meta.get("_is_session_init_request"):
                self.init_meta = deepcopy(request.meta)
            else:
                self.use_meta = deepcopy(request.meta)

    tracker = Tracker()

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com", meta=meta_dict)

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": (1, 1)})

    if outcome:
        # Init request must use responseCookies, not session.
        assert tracker.init_meta["zyte_api"].get("responseCookies") is True
        assert "session" not in tracker.init_meta["zyte_api"]
        # Use request must carry requestCookies, not session.
        assert tracker.use_meta["zyte_api"]["requestCookies"] == _EXPECTED_COOKIES
        assert "session" not in tracker.use_meta["zyte_api"]
    else:
        # Regular session mode: session ID is set, no requestCookies.
        assert "session" in tracker.use_meta["zyte_api"]
        assert "requestCookies" not in tracker.use_meta.get("zyte_api", {})


@deferred_f_from_coro_f
async def test_init_request_has_no_session_id(mockserver):
    """Cookie session init requests do not include the Zyte API session field."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class Tracker:
        def __init__(self):
            self.init_meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            if request.meta.get("_is_session_init_request"):
                self.init_meta = deepcopy(request.meta)

    tracker = Tracker()

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert "session" not in tracker.init_meta["zyte_api"]
    assert tracker.init_meta["zyte_api"]["responseCookies"] is True


@deferred_f_from_coro_f
async def test_use_request_carries_cookies(mockserver):
    """Requests assigned a cookie session carry the cookies from the init
    response as requestCookies."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class Tracker:
        def __init__(self):
            self.use_meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            if not request.meta.get("_is_session_init_request"):
                self.use_meta = deepcopy(request.meta)

    tracker = Tracker()

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": (1, 1)})
    assert tracker.use_meta["zyte_api"]["requestCookies"] == _EXPECTED_COOKIES
    assert "session" not in tracker.use_meta["zyte_api"]
    assert tracker.use_meta[COOKIE_SESSION_ID_META_KEY] is not None


@deferred_f_from_coro_f
async def test_cookie_session_id_meta_key(mockserver):
    """get_request_session_id returns a value for cookie sessions via the
    internal meta key."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    session_id_seen = []

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            session_id_seen.append(get_request_session_id(response.request))

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert len(session_id_seen) == 1
    assert session_id_seen[0] is not None


@deferred_f_from_coro_f
async def test_responsecookies_false_in_params_is_overridden(mockserver, caplog):
    """If params() returns responseCookies=False for a cookie session, it is
    overridden to True and an error is logged."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_PARAMS": {"browserHtml": True, "responseCookies": False},
    }

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    with caplog.at_level(logging.ERROR, logger="scrapy_zyte_api._session"):
        await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": (1, 1)})
    assert "responseCookies" in caplog.text
    assert "forcing it to True" in caplog.text


@deferred_f_from_coro_f
async def test_cookie_jar_cleanup_on_refresh(mockserver):
    """When a cookie session is removed from the pool, its cookies are cleaned
    from the internal cookie jar so they are not leaked to a new session."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    jar_state: list[dict] = []

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            # After the use request, record cookie jar state and trigger a
            # manual refresh to verify cleanup.
            session_id = response.request.meta.get(COOKIE_SESSION_ID_META_KEY)
            mw = None
            assert self.crawler.engine is not None
            for m in self.crawler.engine.downloader.middleware.middlewares:
                if isinstance(m, ScrapyZyteAPISessionDownloaderMiddleware):
                    mw = m
                    break
            if mw is None:
                return
            sm: _SessionManager = mw._sessions
            jar_state.append({"before": dict(sm._cookie_jar)})
            pool = sm.get_pool(response.request)
            sm._start_session_refresh(session_id, response.request, pool)
            jar_state.append({"after": dict(sm._cookie_jar)})

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert len(jar_state) == 2
    # Before refresh: the jar has both the init cookie and the extra cookie
    # merged in from the use response.
    before = jar_state[0]["before"]
    assert len(before) == 1
    session_cookies = next(iter(before.values()))
    assert _EXPECTED_COOKIES[0] in session_cookies
    assert _EXTRA_COOKIE in session_cookies
    # After refresh: that session's cookies have been removed.
    after = jar_state[1]["after"]
    assert len(after) == 0


@deferred_f_from_coro_f
async def test_session_config_cookie_mode_override(mockserver):
    """A SessionConfig subclass can override cookie_mode() to control
    cookie mode per URL pattern."""
    pytest.importorskip("web_poet")

    @session_config(["cookies.example", "plain.example"])
    class CustomSessionConfig(SessionConfig):
        def cookie_mode(self, request: Request) -> bool:
            return "cookies" in urlparse_cached(request).netloc

    settings = {
        **SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    cookie_use_meta: dict[str, Any] = {}
    plain_use_meta: dict[str, Any] = {}

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://cookies.example", "https://plain.example"]

        def parse(self, response):
            if "cookies" in response.url:
                cookie_use_meta.update(deepcopy(response.request.meta))
            else:
                plain_use_meta.update(deepcopy(response.request.meta))

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    # cookies.example uses requestCookies.
    assert "requestCookies" in cookie_use_meta.get("zyte_api", {})
    assert "session" not in cookie_use_meta.get("zyte_api", {})

    # plain.example uses the Zyte API session ID.
    assert "session" in plain_use_meta.get("zyte_api_provider", {})
    assert "requestCookies" not in plain_use_meta.get("zyte_api", {})

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_cookie_session_provider_meta(mockserver):
    """Cookie sessions set requestCookies in zyte_api_provider, not session."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class Tracker:
        def __init__(self):
            self.use_meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            if not request.meta.get("_is_session_init_request"):
                self.use_meta = deepcopy(request.meta)

    tracker = Tracker()

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert "requestCookies" in tracker.use_meta.get("zyte_api_provider", {})
    assert "session" not in tracker.use_meta.get("zyte_api_provider", {})


@deferred_f_from_coro_f
async def test_use_request_has_response_cookies(mockserver):
    """Non-init requests in cookie session mode include responseCookies: True
    so that updated session cookies are captured on each response."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class Tracker:
        def __init__(self):
            self.use_meta: dict[str, Any] = {}

        def track(self, request: Request, spider: Spider):
            if not request.meta.get("_is_session_init_request"):
                self.use_meta = deepcopy(request.meta)

    tracker = Tracker()

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    crawler.signals.connect(tracker.track, signal=signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl())

    assert tracker.use_meta["zyte_api"].get("responseCookies") is True


@deferred_f_from_coro_f
async def test_cookie_jar_updated_from_use_response(mockserver):
    """After each use response, cookies from responseCookies are merged into
    the session cookie jar."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    jar_after_use: list = []

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            session_id = response.request.meta.get(COOKIE_SESSION_ID_META_KEY)
            assert self.crawler.engine is not None
            for m in self.crawler.engine.downloader.middleware.middlewares:
                if isinstance(m, ScrapyZyteAPISessionDownloaderMiddleware):
                    sm: _SessionManager = m._sessions
                    jar_after_use.extend(sm._cookie_jar.get(session_id, []))
                    break

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    # Both the init cookie and the extra cookie from the use response are present.
    assert _EXPECTED_COOKIES[0] in jar_after_use
    assert _EXTRA_COOKIE in jar_after_use


@deferred_f_from_coro_f
async def test_subsequent_requests_carry_updated_cookies(mockserver):
    """When cookies are updated after a use response, the next request for the
    same session carries the merged cookie set."""
    settings = {
        **COOKIE_SESSION_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_POOL_SIZE": 1,
    }

    use_cookies: list[list] = []

    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request("https://example.com")

        def parse(self, response):
            use_cookies.append(
                deepcopy(response.request.meta["zyte_api"]["requestCookies"])
            )
            yield Request("https://example.com", callback=self.parse2, dont_filter=True)

        def parse2(self, response):
            use_cookies.append(
                deepcopy(response.request.meta["zyte_api"]["requestCookies"])
            )

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert len(use_cookies) == 2, f"use_cookies={use_cookies}"
    assert_session_stats(crawler, {"example.com": (1, 2)})
    # First use carries only the init cookie.
    assert use_cookies[0] == _EXPECTED_COOKIES
    # Second use carries both the init cookie and the extra cookie from the
    # first use response.
    assert _EXPECTED_COOKIES[0] in use_cookies[1]
    assert _EXTRA_COOKIE in use_cookies[1]
