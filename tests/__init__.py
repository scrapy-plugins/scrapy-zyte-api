from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from os import environ
from typing import Any, Dict, Optional

from packaging.version import Version
from scrapy import Spider
from scrapy import __version__ as SCRAPY_VERSION
from scrapy.crawler import Crawler
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler as _get_crawler
from zyte_api.aio.client import AsyncClient

from scrapy_zyte_api.addon import Addon
from scrapy_zyte_api.handler import _ScrapyZyteAPIBaseDownloadHandler
from scrapy_zyte_api.utils import _POET_ADDON_SUPPORT

_API_KEY = "a"

DEFAULT_CLIENT_CONCURRENCY = AsyncClient(api_key=_API_KEY).n_conn
SETTINGS_T = Dict[str, Any]
SETTINGS: SETTINGS_T = {
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
    },
    "DOWNLOADER_MIDDLEWARES": {
        "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
        "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
    },
    "REQUEST_FINGERPRINTER_CLASS": "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
    "SPIDER_MIDDLEWARES": {
        "scrapy_zyte_api.ScrapyZyteAPISpiderMiddleware": 100,
        "scrapy_zyte_api.ScrapyZyteAPIRefererSpiderMiddleware": 1000,
    },
    "ZYTE_API_KEY": _API_KEY,
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
}
if Version(SCRAPY_VERSION) < Version("2.12"):
    SETTINGS["REQUEST_FINGERPRINTER_IMPLEMENTATION"] = (
        "2.7"  # Silence deprecation warning
    )

try:
    from scrapy_poet import InjectionMiddleware
except ImportError:
    pass
else:
    assert isinstance(SETTINGS["DOWNLOADER_MIDDLEWARES"], dict)

    if not _POET_ADDON_SUPPORT:
        SETTINGS["DOWNLOADER_MIDDLEWARES"][InjectionMiddleware] = 543

    SETTINGS["SCRAPY_POET_PROVIDERS"] = {
        "scrapy_zyte_api.providers.ZyteApiProvider": 1100
    }

SETTINGS_ADDON: SETTINGS_T = {
    "ADDONS": {
        Addon: 500,
    },
    "ZYTE_API_KEY": _API_KEY,
}
UNSET = object()


class DummySpider(Spider):
    name = "dummy"


async def get_crawler(
    settings=None, spider_cls=DummySpider, setup_engine=True, use_addon=False, poet=True
):
    settings = settings or {}
    base_settings: SETTINGS_T = deepcopy(SETTINGS if not use_addon else SETTINGS_ADDON)
    final_settings = {**base_settings, **settings}
    if poet and _POET_ADDON_SUPPORT:
        final_settings.setdefault("ADDONS", {})["scrapy_poet.Addon"] = 300
    crawler = _get_crawler(settings_dict=final_settings, spidercls=spider_cls)
    if setup_engine:
        await setup_crawler_engine(crawler)
    return crawler


def get_downloader_middleware(crawler, cls):
    for middleware in crawler.engine.downloader.middleware.middlewares:
        if isinstance(middleware, cls):
            return middleware
    class_path = f"{cls.__module__}.{cls.__qualname__}"
    raise ValueError(f"Cannot find downloader middleware {class_path}")


def get_download_handler(crawler, schema):
    return crawler.engine.downloader.handlers._get_handler(schema)


@asynccontextmanager
async def make_handler(
    settings: SETTINGS_T, api_url: Optional[str] = None, *, use_addon: bool = False
):
    if api_url is not None:
        settings["ZYTE_API_URL"] = api_url
    crawler = await get_crawler(settings, use_addon=use_addon)
    handler = get_download_handler(crawler, "https")
    if not isinstance(handler, _ScrapyZyteAPIBaseDownloadHandler):
        # i.e. ZYTE_API_ENABLED=False
        handler = None
    try:
        yield handler
    finally:
        if handler is not None:
            await handler._close()  # NOQA


def serialize_settings(settings):
    result = dict(settings)
    for setting in (
        "ADDONS",
        "ZYTE_API_FALLBACK_HTTP_HANDLER",
        "ZYTE_API_FALLBACK_HTTPS_HANDLER",
    ):
        if setting in settings:
            del result[setting]
    for setting in (
        "DOWNLOADER_MIDDLEWARES",
        "SCRAPY_POET_PROVIDERS",
        "SPIDER_MIDDLEWARES",
    ):
        if setting in result:
            for key in list(result[setting]):
                if isinstance(key, str):
                    obj = load_object(key)
                    result[setting][obj] = result[setting].pop(key)
    for key in result["DOWNLOAD_HANDLERS"]:
        result["DOWNLOAD_HANDLERS"][key] = result["DOWNLOAD_HANDLERS"][key].__class__
    return result


@contextmanager
def set_env(**env_vars):
    old_environ = dict(environ)
    environ.update(env_vars)
    try:
        yield
    finally:
        environ.clear()
        environ.update(old_environ)


async def setup_crawler_engine(crawler: Crawler):
    """Run the crawl steps until engine setup, so that crawler.engine is not
    None.

    https://github.com/scrapy/scrapy/blob/8fbebfa943c3352f5ba49f46531a6ccdd0b52b60/scrapy/crawler.py#L116-L122
    """

    crawler.crawling = True
    crawler.spider = crawler._create_spider()
    crawler.engine = crawler._create_engine()

    handler = get_download_handler(crawler, "https")
    if hasattr(handler, "engine_started"):
        await handler.engine_started()
