import logging

from scrapy.exceptions import IgnoreRequest
from zyte_api.aio.errors import RequestError

from ._params import _ParamParser

logger = logging.getLogger(__name__)


class ScrapyZyteAPIDownloaderMiddleware:
    _slot_prefix = "zyte-api@"

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler) -> None:
        self._param_parser = _ParamParser(crawler, cookies_enabled=False)
        self._crawler = crawler

        self._max_requests = crawler.settings.getint("ZYTE_API_MAX_REQUESTS")
        if self._max_requests:
            logger.info(
                f"Maximum Zyte API requests for this crawl is set at "
                f"{self._max_requests}. The spider will close when it's "
                f"reached."
            )

    def process_request(self, request, spider):
        if self._param_parser.parse(request) is None:
            return

        downloader = self._crawler.engine.downloader
        slot_id = downloader._get_slot_key(request, spider)
        if not isinstance(slot_id, str) or not slot_id.startswith(self._slot_prefix):
            slot_id = f"{self._slot_prefix}{slot_id}"
            request.meta["download_slot"] = slot_id
        _, slot = downloader._get_slot(request, spider)
        slot.delay = 0

        if self._max_requests_reached(downloader):
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


_start_requests_processed = object()


class ForbiddenDomainSpiderMiddleware:
    """Marks start requests and reports to
    :class:`ForbiddenDomainDownloaderMiddleware` the number of them once all
    have been processed."""

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._send_signal = crawler.signals.send_catch_log

    def process_start_requests(self, start_requests, spider):
        count = 0
        for request in start_requests:
            request.meta["is_start_request"] = True
            yield request
            count += 1
        self._send_signal(_start_requests_processed, count=count)


class ForbiddenDomainDownloaderMiddleware:
    """Closes the spider with ``failed-forbidden-domain`` as close reason if
    all start requests get a 451 response from Zyte API."""

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self._failed_start_request_count = 0
        self._total_start_request_count = 0
        crawler.signals.connect(
            self._start_requests_processed, signal=_start_requests_processed
        )
        self._crawler = crawler

    def _start_requests_processed(self, count):
        self._total_start_request_count = count
        self._maybe_close()

    def process_exception(self, request, exception, spider):
        if (
            not request.meta.get("is_start_request")
            or not isinstance(exception, RequestError)
            or exception.status != 451
        ):
            return

        self._failed_start_request_count += 1
        self._maybe_close()

    def _maybe_close(self):
        if not self._total_start_request_count:
            return
        if self._failed_start_request_count < self._total_start_request_count:
            return
        logger.error(
            "Stopping the spider, all start request failed because they "
            "were pointing to a domain forbidden by Zyte API."
        )
        self._crawler.engine.close_spider(
            self._crawler.spider, "failed-forbidden-domain"
        )
