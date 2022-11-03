from .utils import _NEEDS_EARLY_REACTOR

if _NEEDS_EARLY_REACTOR:
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

from ._downloader_middleware import ScrapyZyteAPIDownloaderMiddleware  # NOQA
from ._request_fingerprinter import ScrapyZyteAPIRequestFingerprinter  # NOQA
from .handler import ScrapyZyteAPIDownloadHandler  # NOQA
