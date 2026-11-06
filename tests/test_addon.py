import pytest
from scrapy import Request, Spider
from scrapy.http.response import Response
from scrapy.settings import SETTINGS_PRIORITIES, Settings
from scrapy.settings.default_settings import TWISTED_REACTOR
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from twisted.internet.defer import Deferred, succeed

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPIRefererSpiderMiddleware,
    ScrapyZyteAPISessionDownloaderMiddleware,
    ScrapyZyteAPISessionResetterDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)
from scrapy_zyte_api.addon import Addon
from scrapy_zyte_api.handler import ScrapyZyteAPIHTTPDownloadHandler
from scrapy_zyte_api.utils import (
    _DOWNLOAD_REQUEST_RETURNS_DEFERRED,
    _REACTORLESS_SUPPORT,
)

from . import (
    _FALLBACK_HANDLER_CLS,
    _REACTORLESS,
    _REACTORLESS_HANDLERS,
    deferred_f_from_coro_f,
    download_request,
    get_download_handler,
    make_handler,
    serialize_settings,
)
from . import get_crawler as get_crawler_zyte_api

try:
    import scrapy_poet  # noqa: F401
except ImportError:
    POET = False
    ZyteApiProvider: type | None = None
else:
    POET = True
    from scrapy_zyte_api.providers import ZyteApiProvider

_crawler = get_crawler()
BASELINE_SETTINGS = _crawler.settings.copy_to_dict()


@deferred_f_from_coro_f
async def test_addon(mockserver):
    async with make_handler({}, mockserver.urljoin("/"), use_addon=True) as handler:
        request = Request("https://example.com")
        await download_request(handler, request)
        assert handler._stats.get_value("scrapy-zyte-api/success") == 1


@deferred_f_from_coro_f
async def test_addon_disable_transparent(mockserver):
    async with make_handler(
        {
            "ZYTE_API_FALLBACK_HTTPS_HANDLER": "tests.test_addon.DummyDownloadHandler",
            "ZYTE_API_TRANSPARENT_MODE": False,
        },
        mockserver.urljoin("/"),
        use_addon=True,
    ) as handler:
        request = Request("https://toscrape.com")
        await download_request(handler, request)
        assert handler._stats.get_value("scrapy-zyte-api/success") is None

        meta = {"zyte_api": {"foo": "bar"}}
        request = Request("https://toscrape.com", meta=meta)
        await download_request(handler, request)
        assert handler._stats.get_value("scrapy-zyte-api/success") == 1


@deferred_f_from_coro_f
async def test_addon_fallback():
    crawler = await get_crawler_zyte_api(use_addon=True)
    handler = get_download_handler(crawler, "http")
    assert isinstance(handler, ScrapyZyteAPIHTTPDownloadHandler)
    assert load_object(handler._fallback_handler_path) is _FALLBACK_HANDLER_CLS


class DummyDownloadHandler:
    lazy: bool = False

    if _DOWNLOAD_REQUEST_RETURNS_DEFERRED:

        def download_request(self, request: Request, spider: Spider) -> Deferred:
            return succeed(None)

    else:

        async def download_request(self, request: Request) -> Response:  # type: ignore[misc]
            return None  # type: ignore[return-value]

    async def close(self) -> None:
        pass


@deferred_f_from_coro_f
async def test_addon_fallback_custom():
    settings = {
        "DOWNLOAD_HANDLERS": {"http": "tests.test_addon.DummyDownloadHandler"},
    }
    crawler = await get_crawler_zyte_api(settings, use_addon=True)
    handler = get_download_handler(crawler, "http")
    assert isinstance(handler, ScrapyZyteAPIHTTPDownloadHandler)
    fallback = handler._get_fallback_handler(Request("http://example.com"))
    assert isinstance(fallback, DummyDownloadHandler)
    assert handler._get_fallback_handler(Request("http://example.com")) is fallback


@deferred_f_from_coro_f
async def test_addon_fallback_explicit():
    settings = {
        "ZYTE_API_FALLBACK_HTTP_HANDLER": "tests.test_addon.DummyDownloadHandler",
    }
    crawler = await get_crawler_zyte_api(settings, use_addon=True)
    handler = get_download_handler(crawler, "http")
    assert isinstance(handler, ScrapyZyteAPIHTTPDownloadHandler)
    fallback = handler._get_fallback_handler(Request("http://example.com"))
    assert isinstance(fallback, DummyDownloadHandler)


def test_addon_fallback_default():
    """Without user-defined HTTP(S) download handlers, the add-on leaves the
    fallback settings unset, so that the handlers use the Scrapy defaults,
    which Scrapy only sets after add-ons run when not using a reactor."""
    settings = Settings()
    Addon().update_settings(settings)
    assert settings.get("ZYTE_API_FALLBACK_HTTP_HANDLER") is None
    assert settings.get("ZYTE_API_FALLBACK_HTTPS_HANDLER") is None


def test_addon_disabled():
    base = {
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
            "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
        },
    }
    settings = Settings({**base, "ZYTE_API_ENABLED": False})
    Addon().update_settings(settings)
    assert (
        settings.copy_to_dict()
        == Settings({**base, "ZYTE_API_ENABLED": False}).copy_to_dict()
    )


@pytest.mark.skipif(
    not _REACTORLESS_SUPPORT,
    reason="TWISTED_REACTOR_ENABLED requires Scrapy >= 2.15",
)
def test_addon_reactorless():
    """The add-on forces the asyncio reactor only when a Twisted reactor is in
    use; with TWISTED_REACTOR_ENABLED=False it must leave TWISTED_REACTOR
    untouched."""
    base = {
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
            "https": "scrapy.core.downloader.handlers.http11.HTTP11DownloadHandler",
        },
    }
    enabled = Settings(base)
    Addon().update_settings(enabled)
    assert enabled.getpriority("TWISTED_REACTOR") == SETTINGS_PRIORITIES["addon"]

    disabled = Settings({**base, "TWISTED_REACTOR_ENABLED": False})
    Addon().update_settings(disabled)
    assert disabled.getpriority("TWISTED_REACTOR") != SETTINGS_PRIORITIES["addon"]


@deferred_f_from_coro_f
async def test_addon_matching_settings():
    crawler = await get_crawler_zyte_api(
        {"ZYTE_API_TRANSPARENT_MODE": True}, poet=False
    )
    addon_crawler = await get_crawler_zyte_api(use_addon=True, poet=False)
    assert serialize_settings(crawler.settings) == serialize_settings(
        addon_crawler.settings
    )


@deferred_f_from_coro_f
async def test_addon_custom_fingerprint():
    class CustomRequestFingerprinter:
        pass

    crawler = await get_crawler_zyte_api(
        {"REQUEST_FINGERPRINTER_CLASS": CustomRequestFingerprinter}, use_addon=True
    )
    assert (
        crawler.settings["ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS"]
        == CustomRequestFingerprinter
    )
    assert (
        crawler.settings["REQUEST_FINGERPRINTER_CLASS"]
        == "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter"
    )


def _test_setting_changes(initial_settings, expected_settings):
    settings = {
        **initial_settings,
        "ADDONS": {
            "scrapy_zyte_api.Addon": 500,
        },
    }
    crawler = get_crawler(settings_dict=settings)
    crawler._apply_settings()
    actual_settings = crawler.settings.copy_to_dict()

    # Test separately settings that copy_to_dict messes up.
    for setting in (
        "DOWNLOADER_MIDDLEWARES",
        "SCRAPY_POET_PROVIDERS",
        "SPIDER_MIDDLEWARES",
    ):
        if setting not in crawler.settings:
            assert setting not in expected_settings
            continue
        assert crawler.settings.getdict(setting) == expected_settings.pop(setting)
        del actual_settings[setting]

    for key in BASELINE_SETTINGS:
        if key in actual_settings and actual_settings[key] == BASELINE_SETTINGS[key]:
            del actual_settings[key]
    del actual_settings["ADDONS"]
    assert actual_settings == expected_settings


BASE_EXPECTED = {
    "DOWNLOADER_MIDDLEWARES": {
        ScrapyZyteAPISessionResetterDownloaderMiddleware: 565,
        ScrapyZyteAPIDownloaderMiddleware: 633,
        ScrapyZyteAPISessionDownloaderMiddleware: 667,
    },
    "DOWNLOAD_HANDLERS": {
        # Without a reactor scrapy.utils.test.get_crawler() sets the download
        # handlers for that mode before the add-on overrides HTTP(S) ones.
        **_REACTORLESS_HANDLERS,
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPSDownloadHandler",
    },
    "REQUEST_FINGERPRINTER_CLASS": "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
    "SPIDER_MIDDLEWARES": {
        ScrapyZyteAPISpiderMiddleware: 100,
        ScrapyZyteAPIRefererSpiderMiddleware: 1000,
    },
    "ZYTE_API_TRANSPARENT_MODE": True,
}
if _REACTORLESS:
    # The add-on keeps the HTTP(S) download handlers that get_crawler() sets.
    BASE_EXPECTED["ZYTE_API_FALLBACK_HTTP_HANDLER"] = _REACTORLESS_HANDLERS["http"]
    BASE_EXPECTED["ZYTE_API_FALLBACK_HTTPS_HANDLER"] = _REACTORLESS_HANDLERS["https"]
if (
    not _REACTORLESS
    and TWISTED_REACTOR != "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
):
    BASE_EXPECTED["TWISTED_REACTOR"] = (
        "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
    )


@pytest.mark.skipif(
    POET, reason="Test expectations assume scrapy-poet is not installed"
)
@pytest.mark.parametrize(
    ("initial_settings", "expected_settings"),
    [
        (
            {},
            BASE_EXPECTED,
        ),
        (
            {
                "DOWNLOADER_MIDDLEWARES": {
                    "builtins.str": 123,
                },
            },
            {
                **BASE_EXPECTED,
                "DOWNLOADER_MIDDLEWARES": {
                    "builtins.str": 123,
                    ScrapyZyteAPISessionResetterDownloaderMiddleware: 565,
                    ScrapyZyteAPIDownloaderMiddleware: 633,
                    ScrapyZyteAPISessionDownloaderMiddleware: 667,
                },
            },
        ),
        (
            {
                "DOWNLOADER_MIDDLEWARES": {
                    ScrapyZyteAPIDownloaderMiddleware: 999,
                },
            },
            {
                **BASE_EXPECTED,
                "DOWNLOADER_MIDDLEWARES": {
                    ScrapyZyteAPISessionResetterDownloaderMiddleware: 565,
                    ScrapyZyteAPISessionDownloaderMiddleware: 667,
                    ScrapyZyteAPIDownloaderMiddleware: 999,
                },
            },
        ),
        (
            {
                "DOWNLOADER_MIDDLEWARES": {
                    "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 999,
                },
            },
            {
                **BASE_EXPECTED,
                "DOWNLOADER_MIDDLEWARES": {
                    ScrapyZyteAPISessionResetterDownloaderMiddleware: 565,
                    ScrapyZyteAPISessionDownloaderMiddleware: 667,
                    "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 999,
                },
            },
        ),
    ],
)
def test_no_poet_setting_changes(initial_settings, expected_settings):
    _test_setting_changes(initial_settings, expected_settings)


EXPECTED_DOWNLOADER_MIDDLEWARES = {
    ScrapyZyteAPISessionResetterDownloaderMiddleware: 565,
    ScrapyZyteAPIDownloaderMiddleware: 633,
    ScrapyZyteAPISessionDownloaderMiddleware: 667,
}

_SESSIONS_BASE_EXPECTED = dict(BASE_EXPECTED)
if POET:
    _SESSIONS_BASE_EXPECTED["DOWNLOADER_MIDDLEWARES"] = EXPECTED_DOWNLOADER_MIDDLEWARES
    _SESSIONS_BASE_EXPECTED["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 1100}


@pytest.mark.parametrize(
    ("initial_settings", "expected_settings"),
    [
        # Sessions enabled: addon does not set ZYTE_API_SESSION_RETRY_POLICY.
        (
            {"ZYTE_API_SESSION_ENABLED": True},
            {
                **_SESSIONS_BASE_EXPECTED,
                "ZYTE_API_SESSION_ENABLED": True,
            },
        ),
        # aggressive_retrying: addon still does not set ZYTE_API_SESSION_RETRY_POLICY.
        (
            {
                "ZYTE_API_SESSION_ENABLED": True,
                "ZYTE_API_RETRY_POLICY": "zyte_api.aggressive_retrying",
            },
            {
                **_SESSIONS_BASE_EXPECTED,
                "ZYTE_API_SESSION_ENABLED": True,
                "ZYTE_API_RETRY_POLICY": "zyte_api.aggressive_retrying",
            },
        ),
    ],
)
def test_sessions_setting_changes(initial_settings, expected_settings):
    _test_setting_changes(initial_settings, expected_settings)


@pytest.mark.skipif(
    not POET, reason="Test expectations assume scrapy-poet is installed"
)
@pytest.mark.parametrize(
    ("initial_settings", "expected_settings"),
    [
        (
            {},
            {
                **BASE_EXPECTED,
                "DOWNLOADER_MIDDLEWARES": EXPECTED_DOWNLOADER_MIDDLEWARES,
                "SCRAPY_POET_PROVIDERS": {
                    ZyteApiProvider: 1100,
                },
            },
        ),
    ],
)
def test_poet_setting_changes(initial_settings, expected_settings):
    _test_setting_changes(initial_settings, expected_settings)


@pytest.mark.parametrize(
    ("manual_settings", "addon_settings"),
    [
        # Default: addon does not set ZYTE_API_SESSION_RETRY_POLICY.
        (
            {},
            {},
        ),
        # aggressive_retrying: addon still does not set ZYTE_API_SESSION_RETRY_POLICY.
        (
            {"ZYTE_API_RETRY_POLICY": "zyte_api.aggressive_retrying"},
            {"ZYTE_API_RETRY_POLICY": "zyte_api.aggressive_retrying"},
        ),
    ],
)
@deferred_f_from_coro_f
async def test_sessions(manual_settings, addon_settings):
    crawler = await get_crawler_zyte_api(
        {
            "ZYTE_API_TRANSPARENT_MODE": True,
            "ZYTE_API_SESSION_ENABLED": True,
            **manual_settings,
        },
        poet=False,
    )
    addon_crawler = await get_crawler_zyte_api(
        {"ZYTE_API_SESSION_ENABLED": True, **addon_settings}, use_addon=True, poet=False
    )
    assert serialize_settings(crawler.settings) == serialize_settings(
        addon_crawler.settings
    )
