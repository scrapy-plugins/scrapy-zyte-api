from typing import cast

from scrapy.settings import BaseSettings
from scrapy.utils.misc import load_object
from zyte_api import zyte_api_retrying

from scrapy_zyte_api import (
    ScrapyZyteAPIDownloaderMiddleware,
    ScrapyZyteAPISessionDownloaderMiddleware,
    ScrapyZyteAPISpiderMiddleware,
)


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


# NOTE: We use import paths instead of the classes because retry policy classes
# are not pickleable (https://github.com/jd/tenacity/issues/147), which is a
# Scrapy requirement
# (https://doc.scrapy.org/en/latest/topics/settings.html#compatibility-with-pickle).
_SESSION_RETRY_POLICIES = {
    zyte_api_retrying: "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY",
}

try:
    from zyte_api import aggressive_retrying
except ImportError:
    pass
else:
    _SESSION_RETRY_POLICIES[aggressive_retrying] = (
        "scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY"
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
                cast(int, settings.getpriority("REQUEST_FINGERPRINTER_CLASS")),
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
        settings.set(
            "TWISTED_REACTOR",
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "addon",
        )
        settings.set("ZYTE_API_TRANSPARENT_MODE", True, "addon")

        try:
            from scrapy_poet import InjectionMiddleware
        except ImportError:
            pass
        else:
            from scrapy_zyte_api.providers import ZyteApiProvider

            _setdefault(settings, "DOWNLOADER_MIDDLEWARES", InjectionMiddleware, 543)
            _setdefault(settings, "SCRAPY_POET_PROVIDERS", ZyteApiProvider, 1100)

        if settings.getbool("ZYTE_API_SESSION_ENABLED", False):
            retry_policy = settings.get(
                "ZYTE_API_RETRY_POLICY", "zyte_api.zyte_api_retrying"
            )
            loaded_retry_policy = load_object(retry_policy)
            settings.set(
                "ZYTE_API_RETRY_POLICY",
                _SESSION_RETRY_POLICIES.get(loaded_retry_policy, retry_policy),
                cast(int, settings.getpriority("ZYTE_API_RETRY_POLICY")),
            )
