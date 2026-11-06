import asyncio
import inspect
from collections.abc import Coroutine
from importlib.metadata import version
from typing import Any

import scrapy
from packaging.version import Version
from scrapy.utils.defer import deferred_to_future, maybe_deferred_to_future
from scrapy.utils.reactor import is_asyncio_reactor_installed
from scrapy.utils.reactor import is_reactor_installed as _is_reactor_installed
from twisted.internet.defer import Deferred
from zyte_api.utils import USER_AGENT as PYTHON_ZYTE_API_USER_AGENT

from .__version__ import __version__

USER_AGENT = f"scrapy-zyte-api/{__version__} {PYTHON_ZYTE_API_USER_AGENT}"

_PYTHON_ZYTE_API_VERSION = Version(version("zyte_api"))

_SCRAPY_VERSION = Version(scrapy.__version__)
_SCRAPY_2_14_0 = Version("2.14.0")
_SCRAPY_2_15_0 = Version("2.15.0")

_DOWNLOAD_REQUEST_RETURNS_DEFERRED = _SCRAPY_VERSION < _SCRAPY_2_14_0
_ENGINE_HAS_DOWNLOAD_ASYNC = _SCRAPY_VERSION >= _SCRAPY_2_14_0
_GET_SLOT_NEEDS_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_14_0
_LOG_DEFERRED_IS_DEPRECATED = _SCRAPY_VERSION >= _SCRAPY_2_14_0
_PROCESS_SPIDER_OUTPUT_REQUIRES_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_14_0
_PROCESS_START_REQUIRES_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_14_0
_REACTORLESS_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_15_0

try:
    from zyte_api import AuthInfo  # noqa: F401
except ImportError:
    _X402_SUPPORT = False
else:
    _X402_SUPPORT = True


try:
    from scrapy.utils.asyncio import is_asyncio_available as _is_asyncio_available
except ImportError:  # Scrapy < 2.14

    def _is_asyncio_available() -> bool:
        if not _is_reactor_installed():
            raise RuntimeError(
                "is_asyncio_available() called without an installed reactor."
            )

        return is_asyncio_reactor_installed()


# https://github.com/scrapy/scrapy/blob/0b9d8da09dd2cb1b74ddf025107e6f584839fbff/scrapy/utils/defer.py#L525
def _schedule_coro(coro: Coroutine[Any, Any, Any]) -> None:
    if not _is_asyncio_available():
        Deferred.fromCoroutine(coro)
        return
    loop = asyncio.get_event_loop()
    loop.create_task(coro)  # noqa: RUF006


def _reactor_enabled(settings) -> bool:
    """Return whether Scrapy is meant to run with a Twisted reactor installed.

    ``TWISTED_REACTOR_ENABLED`` was introduced in Scrapy 2.15 to support running
    without a Twisted reactor (see :func:`scrapy.utils.reactorless.is_reactorless`).
    On earlier versions the setting does not exist and a reactor is always used.
    """
    if not _REACTORLESS_SUPPORT:
        return True
    return settings.getbool("TWISTED_REACTOR_ENABLED", True)


def _close_spider(crawler, reason):
    if hasattr(crawler.engine, "close_spider_async"):
        _schedule_coro(crawler.engine.close_spider_async(reason=reason))
    else:
        crawler.engine.close_spider(crawler.spider, reason)


try:
    from scrapy.utils.defer import ensure_awaitable as _ensure_awaitable
except ImportError:  # pragma: no cover
    # Scrapy < 2.14

    def _ensure_awaitable(o):  # type: ignore[no-redef]
        if isinstance(o, Deferred):
            return maybe_deferred_to_future(o)
        if inspect.isawaitable(o):
            return o

        async def coro():
            return o

        return coro()


__all__ = [
    "USER_AGENT",
    "deferred_to_future",
    "maybe_deferred_to_future",
]
