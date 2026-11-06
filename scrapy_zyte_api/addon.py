from typing import cast

from scrapy.settings import BaseSettings
from scrapy.utils.misc import load_object

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPIRefererSpiderMiddleware,
    ScrapyZyteAPISessionDownloaderMiddleware,
    ScrapyZyteAPISessionResetterDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)

from .utils import _reactor_enabled


def _setdefault(settings, setting, cls, pos):
    setting_value = settings[setting]
    if not setting_value:
        settings[setting] = {cls: pos}
        return
    if cls in setting_value:
        return
    for cls_or_path in setting_value:
        if isinstance(cls_or_path, str):
            _cls = load_object(cls_or_path)
            if _cls == cls:
                return
    settings[setting][cls] = pos


class Addon:
    def update_settings(self, settings: BaseSettings) -> None:
        if not settings.getbool("ZYTE_API_ENABLED", True):
            return

        from scrapy.settings.default_settings import (  # noqa: PLC0415
            REQUEST_FINGERPRINTER_CLASS as _SCRAPY_DEFAULT_REQUEST_FINGEPRINTER_CLASS,
        )

        # Store user-defined HTTP(S) download handlers in the fallback
        # settings, unless those fallback settings are already set. Scrapy
        # defaults are left for the handlers to resolve, because without a
        # reactor Scrapy only sets them after add-ons run.
        download_handlers = settings.getdict("DOWNLOAD_HANDLERS")
        for scheme in ("http", "https"):
            setting = f"ZYTE_API_FALLBACK_{scheme.upper()}_HANDLER"
            if not settings.get(setting) and download_handlers.get(scheme):
                settings.set(setting, download_handlers[scheme], "addon")
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
                cast("int", settings.getpriority("REQUEST_FINGERPRINTER_CLASS")),
            )
        else:
            settings.set(
                "REQUEST_FINGERPRINTER_CLASS",
                "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter",
                "addon",
            )

        settings["DOWNLOAD_HANDLERS"]["http"] = (
            "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPDownloadHandler"
        )
        settings["DOWNLOAD_HANDLERS"]["https"] = (
            "scrapy_zyte_api.handler.ScrapyZyteAPIHTTPSDownloadHandler"
        )
        _setdefault(
            settings,
            "DOWNLOADER_MIDDLEWARES",
            ScrapyZyteAPISessionResetterDownloaderMiddleware,
            565,
        )
        _setdefault(
            settings, "DOWNLOADER_MIDDLEWARES", ScrapyZyteAPIDownloaderMiddleware, 633
        )
        _setdefault(
            settings,
            "DOWNLOADER_MIDDLEWARES",
            ScrapyZyteAPISessionDownloaderMiddleware,
            667,
        )
        _setdefault(settings, "SPIDER_MIDDLEWARES", ScrapyZyteAPISpiderMiddleware, 100)
        _setdefault(
            settings, "SPIDER_MIDDLEWARES", ScrapyZyteAPIRefererSpiderMiddleware, 1000
        )
        if _reactor_enabled(settings):
            settings.set(
                "TWISTED_REACTOR",
                "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "addon",
            )
        settings.set("ZYTE_API_TRANSPARENT_MODE", True, "addon")

        try:
            import scrapy_poet  # noqa: F401, PLC0415
        except ImportError:
            pass
        else:
            from scrapy_zyte_api.providers import ZyteApiProvider  # noqa: PLC0415

            _setdefault(settings, "SCRAPY_POET_PROVIDERS", ZyteApiProvider, 1100)
