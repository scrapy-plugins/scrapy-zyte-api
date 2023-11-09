from .utils import _NEEDS_EARLY_REACTOR

if _NEEDS_EARLY_REACTOR:
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from ._middlewares import (
    ForbiddenDomainDownloaderMiddleware,
    ForbiddenDomainSpiderMiddleware,
    ScrapyZyteAPIDownloaderMiddleware,
)
from ._request_fingerprinter import ScrapyZyteAPIRequestFingerprinter
from .handler import ScrapyZyteAPIDownloadHandler
