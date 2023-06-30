from scrapy.settings import BaseSettings

from scrapy_zyte_api import ScrapyZyteAPIDownloaderMiddleware


class ScrapyZyteAPIAddon:
    def update_settings(self, settings: BaseSettings) -> None:
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
