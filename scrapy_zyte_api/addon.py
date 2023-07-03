from typing import Optional

from scrapy.settings import BaseSettings

from scrapy_zyte_api import ScrapyZyteAPIDownloaderMiddleware


class ScrapyZyteAPIAddon:
    @staticmethod
    def _check_settings(settings: BaseSettings) -> Optional[str]:
        if (
            settings.getwithbase("DOWNLOAD_HANDLERS")["http"]
            != "scrapy.core.downloader.handlers.http.HTTPDownloadHandler"
        ):
            return "'http' value in the 'DOWNLOAD_HANDLERS'"
        if (
            settings.getwithbase("DOWNLOAD_HANDLERS")["https"]
            != "scrapy.core.downloader.handlers.http.HTTPDownloadHandler"
        ):
            return "'https' value in the 'DOWNLOAD_HANDLERS'"
        if (
            settings.get("REQUEST_FINGERPRINTER_CLASS")
            != "scrapy.utils.request.RequestFingerprinter"
        ):
            return "'REQUEST_FINGERPRINTER_CLASS'"
        return None

    def update_settings(self, settings: BaseSettings) -> None:
        nondefault_msg = self._check_settings(settings)
        if nondefault_msg:
            raise ValueError(
                f"The {nondefault_msg} setting is set to a custom value, refusing to override it"
            )
        settings["DOWNLOAD_HANDLERS"][
            "http"
        ] = "scrapy_zyte_api.ScrapyZyteAPIDownloadHandler"
        settings["DOWNLOAD_HANDLERS"][
            "https"
        ] = "scrapy_zyte_api.ScrapyZyteAPIDownloadHandler"
        settings["DOWNLOADER_MIDDLEWARES"][ScrapyZyteAPIDownloaderMiddleware] = 1000
        settings.set(
            "REQUEST_FINGERPRINTER_CLASS",
            "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
            "addon",
        )
        settings.set(
            "TWISTED_REACTOR",
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "addon",
        )
