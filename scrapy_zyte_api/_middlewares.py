from logging import getLogger
from warnings import warn

from scrapy import Request, Spider
from scrapy.exceptions import IgnoreRequest, ScrapyDeprecationWarning
from scrapy.utils.python import global_object_name
from zyte_api import RequestError

from ._params import _ParamParser
from .utils import (
    _AUTOTHROTTLE_DONT_ADJUST_DELAY_SUPPORT,
    _GET_SLOT_NEEDS_SPIDER,
    _LOG_DEFERRED_IS_DEPRECATED,
    _close_spider,
    _schedule_coro,
    maybe_deferred_to_future,
)

logger = getLogger(__name__)
_start_requests_processed = object()


class _BaseMiddleware:
    _slot_prefix = "zyte-api@"

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._param_parser = _ParamParser(crawler, cookies_enabled=False)
        self._crawler = crawler
        self._preserve_delay = crawler.settings.getbool(
            "ZYTE_API_PRESERVE_DELAY",
            not crawler.settings.getbool("AUTOTHROTTLE_ENABLED"),
        )

    def slot_request(
        self, request: Request, spider: Spider | None = None, force: bool = False
    ):
        if spider is not None:
            warn(
                f"Passing a 'spider' argument to "
                f"{global_object_name(self.__class__)}.slot_request() is "
                f"deprecated and the argument will be removed in a future "
                f"scrapy-zyte-api version.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

        if not force and self._param_parser.parse(request) is None:
            return

        if _AUTOTHROTTLE_DONT_ADJUST_DELAY_SUPPORT:
            request.meta.setdefault("autothrottle_dont_adjust_delay", True)

        downloader = self._crawler.engine.downloader
        try:
            slot_id = downloader.get_slot_key(request)
        except AttributeError:  # Scrapy < 2.12
            slot_id = downloader._get_slot_key(request, self._crawler.spider)
        if not isinstance(slot_id, str) or not slot_id.startswith(self._slot_prefix):
            slot_id = f"{self._slot_prefix}{slot_id}"
            request.meta["download_slot"] = slot_id
        if not self._preserve_delay:
            args = (self._crawler.spider,) if _GET_SLOT_NEEDS_SPIDER else ()
            _, slot = downloader._get_slot(request, *args)
            slot.delay = 0


class ScrapyZyteAPIDownloaderMiddleware(_BaseMiddleware):
    def __init__(self, crawler) -> None:
        super().__init__(crawler)
        self._forbidden_domain_start_request_count = 0
        self._total_start_request_count = 0

        self._max_requests = crawler.settings.getint("ZYTE_API_MAX_REQUESTS")
        if self._max_requests:
            logger.info(
                f"Maximum Zyte API requests for this crawl is set at "
                f"{self._max_requests}. The spider will close when it's "
                f"reached."
            )
        self._request_count = 0

        crawler.signals.connect(
            self._start_requests_processed, signal=_start_requests_processed
        )
        self._crawler = crawler

    def _get_spm_mw(self):
        spm_mw_classes = []

        try:
            from scrapy_crawlera import CrawleraMiddleware
        except ImportError:
            pass
        else:
            spm_mw_classes.append(CrawleraMiddleware)

        try:
            from scrapy_zyte_smartproxy import ZyteSmartProxyMiddleware
        except ImportError:
            pass
        else:
            spm_mw_classes.append(ZyteSmartProxyMiddleware)

        middlewares = self._crawler.engine.downloader.middleware.middlewares
        for middleware in middlewares:
            if isinstance(middleware, tuple(spm_mw_classes)):
                return middleware
        return None

    def _check_spm_conflict(self):
        checked = getattr(self, "_checked_spm_conflict", False)
        if checked:
            return
        self._checked_spm_conflict = True
        settings = self._crawler.settings
        in_transparent_mode = settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
        spm_mw = self._get_spm_mw()
        spm_is_enabled = spm_mw and spm_mw.is_enabled(self._crawler.spider)
        if not in_transparent_mode or not spm_is_enabled:
            return
        logger.error(
            "Both scrapy-zyte-smartproxy and the transparent mode of "
            "scrapy-zyte-api are enabled. You should only enable one of "
            "those at the same time.\n"
            "\n"
            "To combine requests that use scrapy-zyte-api and requests "
            "that use scrapy-zyte-smartproxy in the same spider:\n"
            "\n"
            "1. Leave scrapy-zyte-smartproxy enabled.\n"
            "2. Disable the transparent mode of scrapy-zyte-api.\n"
            "3. To send a specific request through Zyte API, use "
            "request.meta to set dont_proxy to True and zyte_api_automap "
            "either to True or to a dictionary of extra request fields."
        )
        _close_spider(self._crawler, "plugin_conflict")

    def _start_requests_processed(self, count):
        self._total_start_request_count = count
        self._maybe_close()

    def process_request(self, request: Request, spider: Spider | None = None):
        self._check_spm_conflict()

        if self._param_parser.parse(request) is None:
            return

        self._request_count += 1
        if self._max_requests and self._request_count > self._max_requests:
            _close_spider(self._crawler, "closespider_max_zapi_requests")
            raise IgnoreRequest(
                f"The request {request} is skipped as {self._max_requests} max "
                f"Zyte API requests have been reached."
            )

        self.slot_request(request, force=True)

    def process_exception(
        self, request: Request, exception: Exception, spider: Spider | None = None
    ):
        if (
            not request.meta.get("is_start_request")
            or not isinstance(exception, RequestError)
            or exception.status != 451
        ):
            return

        self._forbidden_domain_start_request_count += 1
        self._maybe_close()

    def _maybe_close(self):
        if not self._total_start_request_count:
            return
        if self._forbidden_domain_start_request_count < self._total_start_request_count:
            return
        logger.error(
            "Stopping the spider, all start requests failed because they "
            "were pointing to a domain forbidden by Zyte API."
        )
        _close_spider(self._crawler, "failed_forbidden_domain")


class ScrapyZyteAPISpiderMiddleware(_BaseMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        if _LOG_DEFERRED_IS_DEPRECATED:
            self._send_signal = crawler.signals.send_catch_log_async
        else:

            async def _send_signal(signal, **kwargs):
                await maybe_deferred_to_future(
                    crawler.signals.send_catch_log_deferred(signal, **kwargs)
                )

            self._send_signal = _send_signal

    @staticmethod
    def _get_header_set(request):
        return {header.strip().lower() for header in request.headers}

    async def process_start(self, start, spider: Spider | None = None):
        # Mark start requests and reports to the downloader middleware the
        # number of them once all have been processed.
        count = 0
        async for item_or_request in start:
            if isinstance(item_or_request, Request):
                count += 1
                item_or_request.meta["is_start_request"] = True
                self._process_output_request(item_or_request)
            yield item_or_request
        await self._send_signal(_start_requests_processed, count=count)

    def process_start_requests(self, start_requests, spider: Spider):
        count = 0
        for item_or_request in start_requests:
            if isinstance(item_or_request, Request):
                count += 1
                item_or_request.meta["is_start_request"] = True
                self._process_output_request(item_or_request)
            yield item_or_request
        _schedule_coro(self._send_signal(_start_requests_processed, count=count))

    def _process_output_request(self, request: Request):
        if "_pre_mw_headers" not in request.meta:
            request.meta["_pre_mw_headers"] = self._get_header_set(request)
        self.slot_request(request)

    def _process_output_item_or_request(self, item_or_request):
        if not isinstance(item_or_request, Request):
            return
        self._process_output_request(item_or_request)

    def process_spider_output(self, response, result, spider: Spider | None = None):
        for item_or_request in result:
            self._process_output_item_or_request(item_or_request)
            yield item_or_request

    async def process_spider_output_async(
        self, response, result, spider: Spider | None = None
    ):
        async for item_or_request in result:
            self._process_output_item_or_request(item_or_request)
            yield item_or_request


class ScrapyZyteAPIRefererSpiderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._default_policy = crawler.settings.get(
            "ZYTE_API_REFERRER_POLICY", "no-referrer"
        )
        self._param_parser = _ParamParser(crawler, cookies_enabled=False)

    def process_spider_output(self, response, result, spider: Spider | None = None):
        for item_or_request in result:
            self._process_output_item_or_request(item_or_request)
            yield item_or_request

    async def process_spider_output_async(
        self, response, result, spider: Spider | None = None
    ):
        async for item_or_request in result:
            self._process_output_item_or_request(item_or_request)
            yield item_or_request

    def _process_output_item_or_request(self, item_or_request):
        if not isinstance(item_or_request, Request):
            return
        self._process_output_request(item_or_request)

    def _process_output_request(self, request: Request):
        if self._is_zyte_api_request(request):
            request.meta.setdefault("referrer_policy", self._default_policy)

    def _is_zyte_api_request(self, request):
        return self._param_parser.parse(request) is not None
