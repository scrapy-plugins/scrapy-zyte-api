from contextlib import asynccontextmanager, contextmanager
from os import environ
from typing import Optional

from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler as _get_crawler
from zyte_api.aio.client import AsyncClient

from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler

_API_KEY = "a"

DEFAULT_CLIENT_CONCURRENCY = AsyncClient(api_key=_API_KEY).n_conn
SETTINGS = {
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
    },
    "ZYTE_API_KEY": _API_KEY,
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
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


@asynccontextmanager
async def make_handler(settings: dict, api_url: Optional[str] = None):
    settings = settings or {}
    settings["ZYTE_API_KEY"] = "a"
    if api_url is not None:
        settings["ZYTE_API_URL"] = api_url
    crawler = get_crawler(settings)
    try:
        handler = create_instance(
            ScrapyZyteAPIDownloadHandler,
            settings=None,
            crawler=crawler,
        )
    except NotConfigured:  # i.e. ZYTE_API_ENABLED=False
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
