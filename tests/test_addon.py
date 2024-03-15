import pytest
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)

pytest.importorskip("scrapy.addons")

try:
    from scrapy_poet import InjectionMiddleware
except ImportError:
    POET = False
    InjectionMiddleware = None
    ZyteApiProvider = None
else:
    POET = True
    from scrapy_zyte_api.providers import ZyteApiProvider

_crawler = get_crawler()
BASELINE_SETTINGS = _crawler.settings.copy_to_dict()


def _test(initial_settings, expected_settings):
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
        ScrapyZyteAPIDownloaderMiddleware: 1000,
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
                    ScrapyZyteAPIDownloaderMiddleware: 1000,
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
                },
            },
        ),
    ),
)
def test_no_poet(initial_settings, expected_settings):
    _test(initial_settings, expected_settings)


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
                    ScrapyZyteAPIDownloaderMiddleware: 1000,
                    InjectionMiddleware: 543,
                },
                "SCRAPY_POET_PROVIDERS": {
                    ZyteApiProvider: 1100,
                },
            },
        ),
    ),
)
def test_poet(initial_settings, expected_settings):
    _test(initial_settings, expected_settings)
