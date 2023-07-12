from contextlib import asynccontextmanager, contextmanager
from os import environ
from typing import Any, Dict, Optional

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.utils.test import get_crawler as _get_crawler
from zyte_api.aio.client import AsyncClient

from scrapy_zyte_api.addon import Addon
from scrapy_zyte_api.handler import _ScrapyZyteAPIBaseDownloadHandler

_API_KEY = "a"

DEFAULT_CLIENT_CONCURRENCY = AsyncClient(api_key=_API_KEY).n_conn
SETTINGS: Dict[str, Any] = {
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
    },
    "REQUEST_FINGERPRINTER_CLASS": "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
    "ZYTE_API_KEY": _API_KEY,
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
}
SETTINGS_ADDON: Dict[str, Any] = {
    "ADDONS": {
        Addon: 1,
    },
    "ZYTE_API_KEY": _API_KEY,
}
UNSET = object()


class DummySpider(Spider):
    name = "dummy"


def get_crawler(settings=None, spider_cls=DummySpider, setup_engine=True):
    settings = settings or {}
    crawler = _get_crawler(settings_dict=settings, spidercls=spider_cls)
    if setup_engine:
        setup_crawler_engine(crawler)
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
    settings: Dict[str, Any], api_url: Optional[str] = None, *, use_addon: bool = False
):
    settings = {**(SETTINGS if not use_addon else SETTINGS_ADDON), **settings}
    if api_url is not None:
        settings["ZYTE_API_URL"] = api_url
    crawler = get_crawler(settings)
    handler = get_download_handler(crawler, "https")
    if not isinstance(handler, _ScrapyZyteAPIBaseDownloadHandler):
        # i.e. ZYTE_API_ENABLED=False
        handler = None
    try:
        yield handler
    finally:
        if handler is not None:
            await handler._close()  # NOQA


@contextmanager
def set_env(**env_vars):
    old_environ = dict(environ)
    environ.update(env_vars)
    try:
        yield
    finally:
        environ.clear()
        environ.update(old_environ)


def setup_crawler_engine(crawler: Crawler):
    """Run the crawl steps until engine setup, so that crawler.engine is not
    None.

    https://github.com/scrapy/scrapy/blob/8fbebfa943c3352f5ba49f46531a6ccdd0b52b60/scrapy/crawler.py#L116-L122
    """

    crawler.crawling = True
    crawler.spider = crawler._create_spider()
    crawler.engine = crawler._create_engine()

    handler = get_download_handler(crawler, "https")
    if hasattr(handler, "engine_started"):
        handler.engine_started()
