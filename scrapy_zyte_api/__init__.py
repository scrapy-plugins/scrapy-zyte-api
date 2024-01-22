from .utils import _NEEDS_EARLY_REACTOR

if _NEEDS_EARLY_REACTOR:
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from ._annotations import ExtractFrom
from ._middlewares import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)
from ._request_fingerprinter import ScrapyZyteAPIRequestFingerprinter
from .handler import ScrapyZyteAPIDownloadHandler
