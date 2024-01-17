import logging
from typing import Optional, Union, cast

from scrapy import Request, Spider, signals
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Response
from zyte_api.aio.errors import RequestError

from ._params import _ParamParser
from .exceptions import ActionError
from .responses import ZyteAPIResponse, ZyteAPITextResponse

logger = logging.getLogger(__name__)


_start_requests_processed = object()


class _BaseMiddleware:
    _slot_prefix = "zyte-api@"

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._param_parser = _ParamParser(crawler, cookies_enabled=False)
        self._crawler = crawler

    def slot_request(self, request, spider, force=False):
        if not force and self._param_parser.parse(request) is None:
            return

        downloader = self._crawler.engine.downloader
        slot_id = downloader._get_slot_key(request, spider)
        if not isinstance(slot_id, str) or not slot_id.startswith(self._slot_prefix):
            slot_id = f"{self._slot_prefix}{slot_id}"
            request.meta["download_slot"] = slot_id
        _, slot = downloader._get_slot(request, spider)
        slot.delay = 0


class ScrapyZyteAPIDownloaderMiddleware(_BaseMiddleware):
    def __init__(self, crawler) -> None:
        super().__init__(crawler)
        self._forbidden_domain_start_request_count = 0
        self._total_start_request_count = 0

        self._retry_action_errors = crawler.settings.getbool(
            "ZYTE_API_ACTION_ERROR_RETRY_ENABLED", True
        )
        self._max_retry_times = crawler.settings.getint("RETRY_TIMES")
        self._priority_adjust = crawler.settings.getint("RETRY_PRIORITY_ADJUST")
        self._load_action_error_handling()

        self._max_requests = crawler.settings.getint("ZYTE_API_MAX_REQUESTS")
        if self._max_requests:
            logger.info(
                f"Maximum Zyte API requests for this crawl is set at "
                f"{self._max_requests}. The spider will close when it's "
                f"reached."
            )

        crawler.signals.connect(self.open_spider, signal=signals.spider_opened)
        crawler.signals.connect(
            self._start_requests_processed, signal=_start_requests_processed
        )

    def _load_action_error_handling(self):
        value = self._crawler.settings.get("ZYTE_API_ACTION_ERROR_HANDLING", "pass")
        if value in ("pass", "ignore", "err"):
            self._action_error_handling = value
        else:
            fallback_value = "pass"
            logger.error(
                f"Setting ZYTE_API_ACTION_ERROR_HANDLING got an unexpected "
                f"value: {value!r}. Falling back to {fallback_value!r}."
            )
            self._action_error_handling = fallback_value

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

    def open_spider(self, spider):
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
        if self._param_parser.parse(request) is None:
            return

        self.slot_request(request, spider, force=True)

        if self._max_requests_reached(self._crawler.engine.downloader):
            self._crawler.engine.close_spider(spider, "closespider_max_zapi_requests")
            raise IgnoreRequest(
                f"The request {request} is skipped as {self._max_requests} max "
                f"Zyte API requests have been reached."
            )

    def _max_requests_reached(self, downloader) -> bool:
        if not self._max_requests:
            return False

        zapi_req_count = self._crawler.stats.get_value("scrapy-zyte-api/processed", 0)
        download_req_count = sum(
            [
                len(slot.transferring)
                for slot_id, slot in downloader.slots.items()
                if slot_id.startswith(self._slot_prefix)
            ]
        )
        total_requests = zapi_req_count + download_req_count
        return total_requests >= self._max_requests

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

    def _handle_action_error(self, response):
        if self._action_error_handling == "pass":
            return response
        elif self._action_error_handling == "ignore":
            raise IgnoreRequest
        else:
            assert self._action_error_handling == "err"
            raise ActionError(response)

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response]:
        if not isinstance(response, (ZyteAPIResponse, ZyteAPITextResponse)):
            return response

        assert response.raw_api_response is not None
        action_error = any(
            "error" in action for action in response.raw_api_response["actions"]
        )
        if not action_error:
            return response

        if not self._retry_action_errors or request.meta.get("dont_retry", False):
            return self._handle_action_error(response)

        return self._retry(
            request, reason="action-error", spider=spider
        ) or self._handle_action_error(response)

    def _retry(
        self,
        request: Request,
        *,
        reason: str,
        spider: Spider,
    ) -> Optional[Request]:
        max_retry_times = request.meta.get("max_retry_times", self._max_retry_times)
        priority_adjust = request.meta.get("priority_adjust", self._priority_adjust)
        return get_retry_request(
            request,
            reason=reason,
            spider=spider,
            max_retry_times=max_retry_times,
            priority_adjust=priority_adjust,
        )


class ScrapyZyteAPISpiderMiddleware(_BaseMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        self._send_signal = crawler.signals.send_catch_log

    def process_start_requests(self, start_requests, spider):
        # Mark start requests and reports to the downloader middleware the
        # number of them once all have been processed.
        count = 0
        for request in start_requests:
            request.meta["is_start_request"] = True
            self.slot_request(request, spider)
            yield request
            count += 1
        self._send_signal(_start_requests_processed, count=count)

    def process_spider_output(self, response, result, spider):
        for item_or_request in result:
            if isinstance(item_or_request, Request):
                self.slot_request(item_or_request, spider)
            yield item_or_request

    async def process_spider_output_async(self, response, result, spider):
        async for item_or_request in result:
            if isinstance(item_or_request, Request):
                self.slot_request(item_or_request, spider)
            yield item_or_request
