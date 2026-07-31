import sys
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from os import environ
from typing import Any
from urllib.request import Request

from packaging.version import Version
from scrapy import Spider
from scrapy import __version__ as SCRAPY_VERSION
from scrapy.crawler import Crawler
from scrapy.http import Response
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler as _get_crawler
from zyte_api import AsyncZyteAPI

from scrapy_zyte_api.addon import Addon
from scrapy_zyte_api.handler import _ScrapyZyteAPIBaseDownloadHandler
from scrapy_zyte_api.utils import (  # type: ignore[attr-defined]
    _DOWNLOAD_REQUEST_RETURNS_DEFERRED,
    _POET_ADDON_SUPPORT,
    _REACTORLESS_SUPPORT,
    _ensure_awaitable,
    maybe_deferred_to_future,
)


def _detect_reactorless() -> bool:
    """Return whether the test suite is running without a Twisted reactor.

    We cannot rely on :func:`scrapy.utils.reactor.is_reactor_installed` here
    because pytest-twisted installs the reactor lazily, after this module is
    imported. Instead we look at the ``--reactor`` command-line option (as set
    by our tox environments): the reactorless environment passes
    ``--reactor=none``, while the reactor-based ones pass ``--reactor=asyncio``.
    """
    if not _REACTORLESS_SUPPORT:
        return False
    argv = f"{environ.get('PYTEST_ADDOPTS', '')} {' '.join(sys.argv)}"
    return any(token in argv for token in ("--reactor=none", "--reactor none"))


_REACTORLESS = _detect_reactorless()

if _REACTORLESS:
    import pytest

    def deferred_f_from_coro_f(coro_f):
        """Reactorless counterpart of ``scrapy.utils.defer.deferred_f_from_coro_f``.

        Without a Twisted reactor the coroutine test functions are run by
        pytest-asyncio instead of pytest-twisted, so we simply mark them
        instead of wrapping them into a Deferred-returning function.
        """
        return pytest.mark.asyncio(coro_f)

else:
    from scrapy.utils.defer import deferred_f_from_coro_f  # noqa: F401

_API_KEY = "a"

UNSET = object()
DEFAULT_CLIENT_CONCURRENCY = AsyncZyteAPI(api_key=_API_KEY).n_conn

SETTINGS_T = dict[str, Any]
SETTINGS: SETTINGS_T = {
    "DOWNLOAD_HANDLERS": {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
    },
    "DOWNLOADER_MIDDLEWARES": {
        "scrapy_zyte_api.ScrapyZyteAPISessionResetterDownloaderMiddleware": 565,
        "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 633,
        "scrapy_zyte_api.ScrapyZyteAPISessionDownloaderMiddleware": 667,
    },
    "REQUEST_FINGERPRINTER_CLASS": "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
    "SPIDER_MIDDLEWARES": {
        "scrapy_zyte_api.ScrapyZyteAPISpiderMiddleware": 100,
        "scrapy_zyte_api.ScrapyZyteAPIRefererSpiderMiddleware": 1000,
    },
    "TELNETCONSOLE_ENABLED": False,
    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
    "ZYTE_API_KEY": _API_KEY,
}
if Version(SCRAPY_VERSION) < Version("2.12"):
    SETTINGS["REQUEST_FINGERPRINTER_IMPLEMENTATION"] = (
        "2.7"  # Silence deprecation warning
    )

# The HTTP(S) handler used as a fallback when a request is not sent through
# Zyte API. Without a Twisted reactor the default Twisted-based handler cannot
# be used, so we rely on the asyncio-based httpx handler instead.
_HTTPX_HANDLER = "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler"

if _REACTORLESS:
    # A reactor must not be requested when running without one.
    del SETTINGS["TWISTED_REACTOR"]
    SETTINGS["TWISTED_REACTOR_ENABLED"] = False

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
    "TELNETCONSOLE_ENABLED": False,
    "ZYTE_API_KEY": _API_KEY,
}
if _REACTORLESS:
    SETTINGS_ADDON["TWISTED_REACTOR_ENABLED"] = False
    # Make the addon capture an asyncio-compatible fallback handler instead of
    # the default Twisted-based one.
    SETTINGS_ADDON["DOWNLOAD_HANDLERS"] = {
        "http": _HTTPX_HANDLER,
        "https": _HTTPX_HANDLER,
    }

SESSION_SETTINGS: SETTINGS_T = {
    "ZYTE_API_SESSION_CREATION_RETRY_DELAY": 0,
    "ZYTE_API_SESSION_DELAY": 0,
    "ZYTE_API_SESSION_ENABLED": True,
    "ZYTE_API_SESSION_QUEUE_WAIT_TIME": 0,
    "ZYTE_API_SESSION_STATS_PER_POOL": True,
}


class DummySpider(Spider):
    name = "dummy"


async def get_crawler(
    settings=None,
    spider_cls=DummySpider,
    setup_engine=True,
    start_handler=False,
    use_addon=False,
    poet=True,
):
    settings = settings or {}
    base_settings: SETTINGS_T = deepcopy(SETTINGS if not use_addon else SETTINGS_ADDON)
    final_settings = {**base_settings, **settings}
    if poet and _POET_ADDON_SUPPORT:
        final_settings.setdefault("ADDONS", {})["scrapy_poet.Addon"] = 300
    crawler = _get_crawler(settings_dict=final_settings, spidercls=spider_cls)
    if setup_engine:
        await setup_crawler_engine(crawler, start_handler=start_handler)
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
    settings: SETTINGS_T, api_url: str | None = None, *, use_addon: bool = False
):
    if api_url is not None:
        settings["ZYTE_API_URL"] = api_url
    crawler = await get_crawler(
        settings, setup_engine=True, start_handler=True, use_addon=use_addon
    )
    handler = get_download_handler(crawler, "https")
    if not isinstance(handler, _ScrapyZyteAPIBaseDownloadHandler):
        # i.e. ZYTE_API_ENABLED=False
        handler = None
    try:
        yield handler
    finally:
        if handler is not None:
            await handler._close()


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


async def setup_crawler_engine(crawler: Crawler, start_handler: bool = False) -> None:
    """Run the crawl steps until engine setup, so that crawler.engine is not
    None.

    https://github.com/scrapy/scrapy/blob/8fbebfa943c3352f5ba49f46531a6ccdd0b52b60/scrapy/crawler.py#L116-L122
    """

    crawler.crawling = True
    crawler.spider = crawler._create_spider()
    crawler.engine = crawler._create_engine()

    if start_handler:
        handler = get_download_handler(crawler, "https")
        if hasattr(handler, "engine_started"):
            await handler.engine_started()


async def download_request(handler, request) -> Response:
    if not _DOWNLOAD_REQUEST_RETURNS_DEFERRED:
        future = handler.download_request(request)
    else:
        future = maybe_deferred_to_future(handler.download_request(request, None))
    return await future


async def process_request(middleware, request) -> Request | None:
    if not _DOWNLOAD_REQUEST_RETURNS_DEFERRED:
        maybe_awaitable = middleware.process_request(request)
    else:
        maybe_awaitable = middleware.process_request(request, spider=None)
    await _ensure_awaitable(maybe_awaitable)


async def process_response(middleware, request, response) -> Request | None:
    if not _DOWNLOAD_REQUEST_RETURNS_DEFERRED:
        maybe_awaitable = middleware.process_response(request, response)
    else:
        maybe_awaitable = middleware.process_response(request, response, spider=None)
    await _ensure_awaitable(maybe_awaitable)


def get_session_stats(crawler):
    return {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
