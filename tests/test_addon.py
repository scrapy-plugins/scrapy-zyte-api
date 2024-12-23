from typing import Optional, Type

import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request
from scrapy.core.downloader.handlers.http import HTTP10DownloadHandler
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISessionDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)
from scrapy_zyte_api.handler import ScrapyZyteAPIHTTPDownloadHandler

from . import get_crawler as get_crawler_zyte_api
from . import get_download_handler, make_handler, serialize_settings

pytest.importorskip("scrapy.addons")

try:
    from scrapy_poet import InjectionMiddleware
except ImportError:
    POET = False
    InjectionMiddleware = None
    ZyteApiProvider: Optional[Type] = None
else:
    POET = True
    from scrapy_zyte_api.providers import ZyteApiProvider

_crawler = get_crawler()
BASELINE_SETTINGS = _crawler.settings.copy_to_dict()


@ensureDeferred
async def test_addon(mockserver):
    async with make_handler({}, mockserver.urljoin("/"), use_addon=True) as handler:
        request = Request("https://example.com")
        await handler.download_request(request, None)
        assert handler._stats.get_value("scrapy-zyte-api/success") == 1


@ensureDeferred
async def test_addon_disable_transparent(mockserver):
    async with make_handler(
        {"ZYTE_API_TRANSPARENT_MODE": False}, mockserver.urljoin("/"), use_addon=True
    ) as handler:
        request = Request("https://toscrape.com")
        await handler.download_request(request, None)
        assert handler._stats.get_value("scrapy-zyte-api/success") is None

        meta = {"zyte_api": {"foo": "bar"}}
        request = Request("https://toscrape.com", meta=meta)
        await handler.download_request(request, None)
        assert handler._stats.get_value("scrapy-zyte-api/success") == 1


@ensureDeferred
async def test_addon_fallback():
    settings = {
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy.core.downloader.handlers.http.HTTP10DownloadHandler"
        },
    }
    crawler = await get_crawler_zyte_api(settings, use_addon=True)
    handler = get_download_handler(crawler, "http")
    assert isinstance(handler, ScrapyZyteAPIHTTPDownloadHandler)
    assert isinstance(handler._fallback_handler, HTTP10DownloadHandler)


@ensureDeferred
async def test_addon_fallback_explicit():
    settings = {
        "ZYTE_API_FALLBACK_HTTP_HANDLER": "scrapy.core.downloader.handlers.http.HTTP10DownloadHandler",
    }
    crawler = await get_crawler_zyte_api(settings, use_addon=True)
    handler = get_download_handler(crawler, "http")
    assert isinstance(handler, ScrapyZyteAPIHTTPDownloadHandler)
    assert isinstance(handler._fallback_handler, HTTP10DownloadHandler)


@ensureDeferred
async def test_addon_matching_settings():
    crawler = await get_crawler_zyte_api({"ZYTE_API_TRANSPARENT_MODE": True})
    addon_crawler = await get_crawler_zyte_api(use_addon=True)
    assert serialize_settings(crawler.settings) == serialize_settings(
        addon_crawler.settings
    )


@ensureDeferred
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
        ScrapyZyteAPIDownloaderMiddleware: 633,
        ScrapyZyteAPISessionDownloaderMiddleware: 667,
    },
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPSDownloadHandler",
    },
    "REQUEST_FINGERPRINTER_CLASS": "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
    "SPIDER_MIDDLEWARES": {
        ScrapyZyteAPISpiderMiddleware: 100,
    },
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "ZYTE_API_FALLBACK_HTTPS_HANDLER": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
    "ZYTE_API_FALLBACK_HTTP_HANDLER": "scrapy.core.downloader.handlers.http.HTTPDownloadHandler",
    "ZYTE_API_TRANSPARENT_MODE": True,
}


@pytest.mark.skipif(
    POET, reason="Test expectations assume scrapy-poet is not installed"
)
@pytest.mark.parametrize(
    ("initial_settings", "expected_settings"),
    (
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
                    ScrapyZyteAPIDownloaderMiddleware: 999,
                    ScrapyZyteAPISessionDownloaderMiddleware: 667,
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
                    "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 999,
                    ScrapyZyteAPISessionDownloaderMiddleware: 667,
                },
            },
        ),
    ),
)
def test_no_poet_setting_changes(initial_settings, expected_settings):
    _test_setting_changes(initial_settings, expected_settings)


@pytest.mark.skipif(
    not POET, reason="Test expectations assume scrapy-poet is installed"
)
@pytest.mark.parametrize(
    ("initial_settings", "expected_settings"),
    (
        (
            {},
            {
                **BASE_EXPECTED,
                "DOWNLOADER_MIDDLEWARES": {
                    ScrapyZyteAPIDownloaderMiddleware: 633,
                    ScrapyZyteAPISessionDownloaderMiddleware: 667,
                    InjectionMiddleware: 543,
                },
                "SCRAPY_POET_PROVIDERS": {
                    ZyteApiProvider: 1100,
                },
            },
        ),
    ),
)
def test_poet_setting_changes(initial_settings, expected_settings):
    _test_setting_changes(initial_settings, expected_settings)
