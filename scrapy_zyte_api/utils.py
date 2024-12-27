from importlib.metadata import version

import scrapy
from packaging.version import Version
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

# Need to install an asyncio reactor before download handler imports to work
# around:
# https://github.com/scrapy/scrapy/commit/0946eb335a285e1f210ba1185a564699f53b17d8
# Fixed in:
# https://github.com/scrapy/scrapy/commit/e4bdd1cb958b7d89b86ea66f0af1cec2d91a6d44
_NEEDS_EARLY_REACTOR = _SCRAPY_2_4_0 <= _SCRAPY_VERSION < _SCRAPY_2_6_0

_DOWNLOAD_NEEDS_SPIDER = _SCRAPY_VERSION < _SCRAPY_2_6_0
_RAW_CLASS_SETTING_SUPPORT = _SCRAPY_VERSION >= _SCRAPY_2_4_0
_REQUEST_ERROR_HAS_QUERY = _PYTHON_ZYTE_API_VERSION >= _PYTHON_ZYTE_API_0_5_2
_RESPONSE_HAS_ATTRIBUTES = _SCRAPY_VERSION >= _SCRAPY_2_6_0
_RESPONSE_HAS_IP_ADDRESS = _SCRAPY_VERSION >= _SCRAPY_2_1_0
_RESPONSE_HAS_PROTOCOL = _SCRAPY_VERSION >= _SCRAPY_2_5_0

try:
    from scrapy.utils.misc import build_from_crawler as _build_from_crawler
except ImportError:  # Scrapy < 2.12
    from typing import Any, TypeVar

    from scrapy.crawler import Crawler
    from scrapy.utils.misc import create_instance

    T = TypeVar("T")

    def _build_from_crawler(
        objcls: type[T], crawler: Crawler, /, *args: Any, **kwargs: Any
    ) -> T:
        return create_instance(objcls, None, crawler, *args, **kwargs)
