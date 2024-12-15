from logging import getLogger
from typing import cast

from scrapy import Request
from scrapy.exceptions import IgnoreRequest
from zyte_api import RequestError

from ._params import _ParamParser

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

    def slot_request(self, request, spider, force=False):
        if not force and self._param_parser.parse(request) is None:
            return

        downloader = self._crawler.engine.downloader
        try:
            slot_id = downloader.get_slot_key(request)
        except AttributeError:  # Scrapy < 2.12
            slot_id = downloader._get_slot_key(request, spider)
        if not isinstance(slot_id, str) or not slot_id.startswith(self._slot_prefix):
            slot_id = f"{self._slot_prefix}{slot_id}"
            request.meta["download_slot"] = slot_id
        if not self._preserve_delay:
            _, slot = downloader._get_slot(request, spider)
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

    def _check_spm_conflict(self, spider):
        checked = getattr(self, "_checked_spm_conflict", False)
        if checked:
            return
        self._checked_spm_conflict = True
        settings = self._crawler.settings
        in_transparent_mode = settings.getbool("ZYTE_API_TRANSPARENT_MODE", False)
        spm_mw = self._get_spm_mw()
        spm_is_enabled = spm_mw and spm_mw.is_enabled(spider)
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
        from twisted.internet import reactor
        from twisted.internet.interfaces import IReactorCore

        reactor = cast(IReactorCore, reactor)
        reactor.callLater(
            0, self._crawler.engine.close_spider, spider, "plugin_conflict"
        )

    def _start_requests_processed(self, count):
        self._total_start_request_count = count
        self._maybe_close()

    def process_request(self, request, spider):
        self._check_spm_conflict(spider)

        if self._param_parser.parse(request) is None:
            return

        self._request_count += 1
        if self._max_requests and self._request_count > self._max_requests:
            self._crawler.engine.close_spider(spider, "closespider_max_zapi_requests")
            raise IgnoreRequest(
                f"The request {request} is skipped as {self._max_requests} max "
                f"Zyte API requests have been reached."
            )

        self.slot_request(request, spider, force=True)

    def process_exception(self, request, exception, spider):
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
        self._crawler.engine.close_spider(
            self._crawler.spider, "failed_forbidden_domain"
        )


class ScrapyZyteAPISpiderMiddleware(_BaseMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        self._send_signal = crawler.signals.send_catch_log

    @staticmethod
    def _get_header_set(request):
        return {header.strip().lower() for header in request.headers}

    def process_start_requests(self, start_requests, spider):
        # Mark start requests and reports to the downloader middleware the
        # number of them once all have been processed.
        count = 0
        for request in start_requests:
            request.meta["is_start_request"] = True
            self._process_output_request(request, spider)
            yield request
            count += 1
        self._send_signal(_start_requests_processed, count=count)

    def _process_output_request(self, request, spider):
        request.meta["_pre_mw_headers"] = self._get_header_set(request)
        self.slot_request(request, spider)

    def _process_output_item_or_request(self, item_or_request, spider):
        if not isinstance(item_or_request, Request):
            return
        self._process_output_request(item_or_request, spider)

    def process_spider_output(self, response, result, spider):
        for item_or_request in result:
            self._process_output_item_or_request(item_or_request, spider)
            yield item_or_request

    async def process_spider_output_async(self, response, result, spider):
        async for item_or_request in result:
            self._process_output_item_or_request(item_or_request, spider)
            yield item_or_request
