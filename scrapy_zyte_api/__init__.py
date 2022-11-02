from .utils import _NEEDS_EARLY_REACTOR

if _NEEDS_EARLY_REACTOR:
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from scrapy_zyte_api._request_fingerprinter import (  # NOQA
    ScrapyZyteAPIRequestFingerprinter,
)
from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler  # NOQA
