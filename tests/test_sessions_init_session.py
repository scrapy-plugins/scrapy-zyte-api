import pytest

pytest.importorskip("web_poet")

from scrapy import Request, Spider
from scrapy.utils.defer import deferred_f_from_coro_f

from scrapy_zyte_api import SessionConfig, is_session_init_request, session_config
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, get_crawler
from .helpers import assert_session_stats


@deferred_f_from_coro_f
async def test_init_session_chain(mockserver):
    """init_session can run multiple downloads in sequence; the download helper
    injects session ID, SESSION_INIT_META_KEY, and dont_merge_cookies=True."""
    steps_run = []
    verifications = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r = await download(
                Request(
                    "https://example.com",
                    meta={"zyte_api": {"browserHtml": True}},
                )
            )
            verifications.append(
                {
                    "session_id_matches": r.raw_api_response["session"]["id"]
                    == session_id,
                    "is_init_request": is_session_init_request(r.request),
                    "dont_merge_cookies": r.request.meta.get("dont_merge_cookies"),
                }
            )
            steps_run.append(1)
            await download(
                Request(
                    "https://example.com",
                    meta={"zyte_api": {"browserHtml": True}},
                )
            )
            steps_run.append(2)
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert steps_run == [1, 2]
    assert verifications == [
        {
            "session_id_matches": True,
            "is_init_request": True,
            "dont_merge_cookies": True,
        }
    ]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_init_session_overrides(mockserver):
    """Setting session=None suppresses session injection; setting
    dont_merge_cookies explicitly in meta overrides the default True."""
    results = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r1 = await download(
                Request(
                    "https://example.com",
                    meta={"zyte_api": {"browserHtml": True, "session": None}},
                )
            )
            r2 = await download(
                Request(
                    "https://example.com",
                    meta={
                        "zyte_api": {"browserHtml": True},
                        "dont_merge_cookies": False,
                    },
                )
            )
            results.append(
                {
                    "session_suppressed": "session" not in r1.raw_api_response,
                    "dont_merge_cookies_override": r2.request.meta.get(
                        "dont_merge_cookies"
                    ),
                }
            )
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert results == [
        {"session_suppressed": True, "dont_merge_cookies_override": False}
    ]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("behavior", "expected_stat"),
    [
        ("return_false", "init/check-failed"),
        ("raise", "init/failed"),
    ],
)
@deferred_f_from_coro_f
async def test_init_session_failure(mockserver, behavior, expected_stat):
    """Returning False counts as init/check-failed; raising counts as init/failed."""

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            if behavior == "return_false":
                return False
            raise RuntimeError("chain failed")

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert_session_stats(crawler, {"example.com": {expected_stat: 1}})

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_init_session_download_automap(mockserver):
    """When init_session calls download with a zyte_api_automap request, the
    session ID is injected into zyte_api_automap (not zyte_api)."""
    results = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r = await download(
                Request(
                    "https://example.com",
                    meta={"zyte_api_automap": {"browserHtml": True}},
                )
            )
            results.append(
                {
                    "zyte_api_not_added": "zyte_api" not in r.request.meta,
                    "session_id_matches": r.raw_api_response["session"]["id"]
                    == session_id,
                    "session_in_automap": r.request.meta.get("zyte_api_automap", {})
                    .get("session", {})
                    .get("id")
                    == session_id,
                }
            )
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert results == [
        {
            "zyte_api_not_added": True,
            "session_id_matches": True,
            "session_in_automap": True,
        }
    ]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_init_session_download_session_preset(mockserver):
    """When init_session calls download with 'session' already set in the
    request, the session id is preserved."""
    results = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r = await download(
                Request(
                    "https://example.com",
                    meta={
                        "zyte_api": {"browserHtml": True, "session": {"id": "pre-set"}}
                    },
                )
            )
            results.append(r.request.meta["zyte_api"].get("session", {}).get("id"))
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert results == ["pre-set"]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_init_session_download_session_extra_keys(mockserver):
    """When init_session calls download with a 'session' dict that does not set
    'id', the session id is injected while preserving the other session keys."""
    results = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r = await download(
                Request(
                    "https://example.com",
                    meta={
                        "zyte_api": {
                            "browserHtml": True,
                            "session": {"extraKey": "value"},
                        }
                    },
                )
            )
            session = r.request.meta["zyte_api"]["session"]
            results.append(
                {
                    "id_matches": session.get("id") == session_id,
                    "extra_key_preserved": session.get("extraKey") == "value",
                    "echoed": r.raw_api_response["session"] == session,
                }
            )
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert results == [
        {"id_matches": True, "extra_key_preserved": True, "echoed": True}
    ]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_init_session_download_automap_session_none(mockserver):
    """When init_session calls download with session=None in zyte_api_automap,
    session injection is suppressed for that request."""
    results = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r = await download(
                Request(
                    "https://example.com",
                    meta={"zyte_api_automap": {"browserHtml": True, "session": None}},
                )
            )
            results.append("session" not in r.raw_api_response)
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert results == [True]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]


@pytest.mark.parametrize("transparent_mode", [False, True])
@deferred_f_from_coro_f
async def test_init_session_download_bare_request(mockserver, transparent_mode):
    """A bare init request (no explicit Zyte API metadata) always goes through
    Zyte API: the session ID is injected into zyte_api_automap (not zyte_api),
    regardless of whether transparent mode is enabled."""
    results = []

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        async def init_session(self, session_id, request, download):
            r = await download(Request("https://example.com"))
            results.append(
                {
                    "zyte_api_not_added": "zyte_api" not in r.request.meta,
                    "session_id_matches": r.raw_api_response["session"]["id"]
                    == session_id,
                    "session_in_automap": r.request.meta.get("zyte_api_automap", {})
                    .get("session", {})
                    .get("id")
                    == session_id,
                }
            )
            return True

    settings = {
        **SESSION_SETTINGS,
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_TRANSPARENT_MODE": transparent_mode,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert results == [
        {
            "zyte_api_not_added": True,
            "session_id_matches": True,
            "session_in_automap": True,
        }
    ]
    assert_session_stats(crawler, {"example.com": (1, 1)})

    session_config_registry.__init__()  # type: ignore[misc]
