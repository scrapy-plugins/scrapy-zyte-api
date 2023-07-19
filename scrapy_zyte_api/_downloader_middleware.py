import logging

from scrapy.exceptions import IgnoreRequest

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
                f"{self._max_requests}. Spider will close when it's reached."
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

        if (
            self._max_requests
            and self._zapi_req_count() + self._download_req_count(downloader)
            >= self._max_requests
        ):
            self._crawler.engine.close_spider(spider, "closespider_max_zapi_requests")
            self._crawler.engine.downloader.close()
            raise IgnoreRequest("Reached max Zyte API requests")

    def _zapi_req_count(self) -> int:
        return self._crawler.stats.get_value("scrapy-zyte-api/processed", 0)

    def _download_req_count(self, downloader) -> int:
        return sum(
            [
                len(slot.transferring)
                for slot_id, slot in downloader.slots.items()
                if slot_id.startswith(self._slot_prefix)
            ]
        )
