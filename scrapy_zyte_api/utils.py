import asyncio
import sys
from importlib.metadata import version
from typing import Any, Coroutine
from warnings import catch_warnings, filterwarnings

import scrapy
from packaging.version import Version
from scrapy.utils.reactor import is_asyncio_reactor_installed
from zyte_api.utils import USER_AGENT as PYTHON_ZYTE_API_USER_AGENT

from .__version__ import __version__

USER_AGENT = f"scrapy-zyte-api/{__version__} {PYTHON_ZYTE_API_USER_AGENT}"

_PYTHON_ZYTE_API_VERSION = Version(version("zyte_api"))
_PYTHON_ZYTE_API_0_5_2 = Version("0.5.2")

_SCRAPY_VERSION = Version(scrapy.__version__)
_SCRAPY_2_1_0 = Version("2.1.0")
_SCRAPY_2_4_0 = Version("2.4.0")
_SCRAPY_2_5_0 = Version("2.5.0")
_SCRAPY_2_6_0 = Version("2.6.0")
_SCRAPY_2_7_0 = Version("2.7.0")
_SCRAPY_2_10_0 = Version("2.10.0")
_SCRAPY_2_12_0 = Version("2.12.0")
_SCRAPY_2_13_0 = Version("2.13.0")
_SCRAPY_2_14_0 = Version("2.14.0")

# Need to install an asyncio reactor before download handler imports to work
# around:
# https://github.com/scrapy/scrapy/commit/0946eb335a285e1f210ba1185a564699f53b17d8
# Fixed in:
# https://github.com/scrapy/scrapy/commit/e4bdd1cb958b7d89b86ea66f0af1cec2d91a6d44
_NEEDS_EARLY_REACTOR = _SCRAPY_2_4_0 <= _SCRAPY_VERSION < _SCRAPY_2_6_0

_ADDON_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_10_0
_ASYNC_START_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_13_0
_AUTOTHROTTLE_DONT_ADJUST_DELAY_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_12_0
_DOWNLOAD_NEEDS_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_6_0
_DOWNLOAD_REQUEST_RETURNS_DEFERRED = _SCRAPY_VERSION < _SCRAPY_2_14_0
_ENGINE_HAS_DOWNLOAD_ASYNC = _SCRAPY_VERSION >= _SCRAPY_2_14_0
_GET_SLOT_NEEDS_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_14_0
_LOG_DEFERRED_IS_DEPRECATED = _SCRAPY_VERSION >= _SCRAPY_2_14_0
_PROCESS_SPIDER_OUTPUT_ASYNC_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_7_0
_PROCESS_SPIDER_OUTPUT_REQUIRES_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_14_0
_PROCESS_START_REQUIRES_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_14_0
_RAW_CLASS_SETTING_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_4_0
_REQUEST_ERROR_HAS_QUERY = _PYTHON_ZYTE_API_VERSION >= _PYTHON_ZYTE_API_0_5_2
_RESPONSE_HAS_ATTRIBUTES = _SCRAPY_VERSION >= _SCRAPY_2_6_0
_RESPONSE_HAS_IP_ADDRESS = _SCRAPY_VERSION >= _SCRAPY_2_1_0
_RESPONSE_HAS_PROTOCOL = _SCRAPY_VERSION >= _SCRAPY_2_5_0
_START_REQUESTS_CAN_YIELD_ITEMS = _SCRAPY_VERSION >= _SCRAPY_2_12_0

try:
    from scrapy.utils.misc import build_from_crawler as _build_from_crawler
except ImportError:  # Scrapy < 2.12
    from typing import Any, TypeVar

    from scrapy.crawler import Crawler
    from scrapy.utils.misc import create_instance  # type: ignore[attr-defined]

    T = TypeVar("T")

    def _build_from_crawler(
        objcls: type[T], crawler: Crawler, /, *args: Any, **kwargs: Any
    ) -> T:
        return create_instance(objcls, None, crawler, *args, **kwargs)


try:
    import scrapy_poet  # noqa: F401
except ImportError:
    _POET_ADDON_SUPPORT = False
else:
    _SCRAPY_POET_VERSION = Version(version("scrapy-poet"))
    _SCRAPY_POET_0_26_0 = Version("0.26.0")
    _POET_ADDON_SUPPORT = _SCRAPY_POET_VERSION >= _SCRAPY_POET_0_26_0

try:
    from zyte_api import AuthInfo  # noqa: F401
except ImportError:
    _X402_SUPPORT = False
else:
    _X402_SUPPORT = True


try:
    from scrapy.utils.defer import deferred_to_future, maybe_deferred_to_future
except ImportError:  # Scrapy < 2.7.0
    import asyncio
    from typing import TYPE_CHECKING, TypeVar, Union
    from warnings import catch_warnings, filterwarnings

    if TYPE_CHECKING:
        from twisted.internet.defer import Deferred

    def set_asyncio_event_loop():
        try:
            with catch_warnings():
                filterwarnings(
                    "ignore",
                    message="There is no current event loop",
                    category=DeprecationWarning,
                )
                event_loop = asyncio.get_event_loop()
        except RuntimeError:
            event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(event_loop)
        return event_loop

    def _get_asyncio_event_loop():
        return set_asyncio_event_loop()

    _T = TypeVar("_T")

    def deferred_to_future(d: "Deferred[_T]") -> "asyncio.Future[_T]":
        return d.asFuture(_get_asyncio_event_loop())

    def maybe_deferred_to_future(
        d: "Deferred[_T]",
    ) -> Union["Deferred[_T]", "asyncio.Future[_T]"]:
        if not is_asyncio_reactor_installed():
            return d
        return deferred_to_future(d)


try:
    from scrapy.utils.reactor import is_reactor_installed as _is_reactor_installed
except ImportError:  # Scrapy < 2.14

    def _is_reactor_installed() -> bool:
        return "twisted.internet.reactor" in sys.modules


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
        from twisted.internet.defer import Deferred

        Deferred.fromCoroutine(coro)
        return
    loop = asyncio.get_event_loop()
    loop.create_task(coro)  # noqa: RUF006


def _close_spider(crawler, reason):
    if hasattr(crawler.engine, "close_spider_async"):
        _schedule_coro(crawler.engine.close_spider_async(reason=reason))
    else:
        crawler.engine.close_spider(crawler.spider, reason)


try:
    from scrapy.utils.defer import ensure_awaitable as _ensure_awaitable
except ImportError:  # pragma: no cover
    # Scrapy < 2.14

    import inspect

    from twisted.internet.defer import Deferred

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
