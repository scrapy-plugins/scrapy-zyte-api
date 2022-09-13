import scrapy
from packaging.version import Version

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

_RESPONSE_HAS_ATTRIBUTES = _SCRAPY_VERSION >= _SCRAPY_2_6_0
_RESPONSE_HAS_IP_ADDRESS = _SCRAPY_VERSION >= _SCRAPY_2_1_0
_RESPONSE_HAS_PROTOCOL = _SCRAPY_VERSION >= _SCRAPY_2_5_0
