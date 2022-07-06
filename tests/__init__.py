from contextlib import asynccontextmanager, contextmanager
from os import environ
from typing import Optional

from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler
from twisted.internet.asyncioreactor import AsyncioSelectorReactor
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
    "TWISTED_REACTOR": AsyncioSelectorReactor,
}
UNSET = object()


@asynccontextmanager
async def make_handler(settings: dict, api_url: Optional[str] = None):
    settings = settings or {}
    settings["ZYTE_API_KEY"] = "a"
    if api_url is not None:
        settings["ZYTE_API_URL"] = api_url
    crawler = get_crawler(settings_dict=settings)
    handler = create_instance(
        ScrapyZyteAPIDownloadHandler,
        settings=None,
        crawler=crawler,
    )
    try:
        yield handler
    finally:
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
