from scrapy.settings import BaseSettings
from scrapy.utils.misc import load_object

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)


class Addon:
    def update_settings(self, settings: BaseSettings) -> None:
        from scrapy.settings.default_settings import (
            REQUEST_FINGERPRINTER_CLASS as _SCRAPY_DEFAULT_REQUEST_FINGEPRINTER_CLASS,
        )

        # Read the current values of the settings and store them in the fallback settings,
        # unless those fallback settings are already set.
        if not settings.get("ZYTE_API_FALLBACK_HTTP_HANDLER"):
            settings.set(
                "ZYTE_API_FALLBACK_HTTP_HANDLER",
                settings.getwithbase("DOWNLOAD_HANDLERS")["http"],
                "addon",
            )
        if not settings.get("ZYTE_API_FALLBACK_HTTPS_HANDLER"):
            settings.set(
                "ZYTE_API_FALLBACK_HTTPS_HANDLER",
                settings.getwithbase("DOWNLOAD_HANDLERS")["https"],
                "addon",
            )
        if not settings.get("ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS") and (
            load_object(settings.get("REQUEST_FINGERPRINTER_CLASS"))
            is not load_object(_SCRAPY_DEFAULT_REQUEST_FINGEPRINTER_CLASS)
        ):
            settings.set(
                "ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS",
                settings.get("REQUEST_FINGERPRINTER_CLASS"),
                "addon",
            )
            settings.set(
                "REQUEST_FINGERPRINTER_CLASS",
                "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
                settings.getpriority("REQUEST_FINGERPRINTER_CLASS"),
            )
        else:
            settings.set(
                "REQUEST_FINGERPRINTER_CLASS",
                "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
                "addon",
            )

        settings["DOWNLOAD_HANDLERS"][
            "http"
        ] = "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPDownloadHandler"
        settings["DOWNLOAD_HANDLERS"][
            "https"
        ] = "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPSDownloadHandler"
        settings["DOWNLOADER_MIDDLEWARES"][ScrapyZyteAPIDownloaderMiddleware] = 1000
        settings["SPIDER_MIDDLEWARES"][ScrapyZyteAPISpiderMiddleware] = 100
        settings.set(
            "TWISTED_REACTOR",
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "addon",
        )
        settings.set("ZYTE_API_TRANSPARENT_MODE", True, "addon")

        try:
            import scrapy_poet  # noqa: F401
        except ImportError:
            pass
        else:
            settings["DOWNLOADER_MIDDLEWARES"]["scrapy_poet.InjectionMiddleware"] = 543
