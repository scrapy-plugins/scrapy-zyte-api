from logging import getLogger
from typing import Any, Set, Type

from itemadapter import ItemAdapter
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import load_object
from scrapy_poet import InjectionMiddleware
from web_poet.fields import get_fields_dict
from web_poet.utils import get_fq_class_name
from zyte_common_items.fields import is_auto_field

logger = getLogger(__name__)


class ScrapyZyteAPIAutoFieldStatsItemPipeline:

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("ZYTE_API_AUTO_FIELD_STATS", False):
            raise NotConfigured

        raw_url_fields = crawler.settings.getdict("ZYTE_API_AUTO_FIELD_URL_FIELDS", {})
        self._url_fields = {load_object(k): v for k, v in raw_url_fields.items()}
        self._seen: Set[Type] = set()
        self._crawler = crawler
        self._stats = crawler.stats
        self._item_cls_without_url: Set[Type] = set()

    def open_spider(self, spider):
        for component in self._crawler.engine.downloader.middleware.middlewares:
            if isinstance(component, InjectionMiddleware):
                self._registry = component.injector.registry
                return
        raise RuntimeError(
            "Could not find scrapy_poet.InjectionMiddleware among downloader "
            "middlewares. scrapy-poet may be misconfigured."
        )

    def process_item(self, item: Any, spider: Spider):
        item_cls = item.__class__

        url_field = self._url_fields.get(item_cls, "url")
        adapter = ItemAdapter(item)
        url = adapter.get(url_field, None)
        if not url:
            if item_cls not in self._item_cls_without_url:
                self._item_cls_without_url.add(item_cls)
                logger.warning(
                    f"An item of type {item_cls} was missing a non-empty URL "
                    f"in its {url_field!r} field. An item URL is necessary to "
                    f"determine the page object that was used to generate "
                    f"that item, and hence print the auto field stats that "
                    f"you requested by enabling the ZYTE_API_AUTO_FIELD_STATS "
                    f"setting. If {url_field!r} is the wrong URL field for "
                    f"that item type, use the ZYTE_API_AUTO_FIELD_URL_FIELDS "
                    f"setting to set a different field."
                )
            return item

        page_cls = self._registry.page_cls_for_item(url, item_cls)

        cls = page_cls or item_cls
        if cls in self._seen:
            return item
        self._seen.add(cls)

        if not page_cls:
            field_list = "(all fields)"
        else:
            auto_fields = set()
            missing_fields = False
            for field_name in get_fields_dict(page_cls):
                if is_auto_field(page_cls, field_name):  # type: ignore[arg-type]
                    auto_fields.add(field_name)
                else:
                    missing_fields = True
            if missing_fields:
                field_list = " ".join(sorted(auto_fields))
            else:
                field_list = "(all fields)"

        cls_fqn = get_fq_class_name(cls)
        self._stats.set_value(f"scrapy-zyte-api/auto_fields/{cls_fqn}", field_list)
        return item
