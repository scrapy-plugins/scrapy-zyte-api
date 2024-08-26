from collections import defaultdict
from typing import Optional

import pytest

pytest.importorskip("scrapy_poet")

import attrs
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy_poet import DummyResponse
from scrapy_poet.utils.testing import HtmlResource, crawl_single_item
from web_poet import ItemPage, default_registry, field, handle_urls
from zyte_common_items import AutoProductPage, BaseProductPage, Item, Product
from zyte_common_items.fields import auto_field

from scrapy_zyte_api.providers import ZyteApiProvider

from .test_providers import create_scrapy_settings


@ensureDeferred
async def test_not_enabled(mockserver):
    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(TestSpider, HtmlResource, settings)

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {}


@ensureDeferred
async def test_no_override(mockserver):
    """When requesting an item directly from Zyte API, without an override to
    change fields, stats reflect the entire list of item fields."""

    from scrapy.statscollectors import MemoryStatsCollector

    duplicate_stat_calls: defaultdict[str, int] = defaultdict(int)

    class OnlyOnceStatsCollector(MemoryStatsCollector):

        def track_duplicate_stat_calls(self, key):
            if key.startswith("scrapy-zyte-api/auto_fields/") and key in self._stats:
                duplicate_stat_calls[key] += 1

        def set_value(self, key, value, spider=None):
            self.track_duplicate_stat_calls(key)
            super().set_value(key, value, spider)

        def inc_value(self, key, count=1, start=1, spider=None):
            self.track_duplicate_stat_calls(key)
            super().inc_value(key, count, start, spider)

        def max_value(self, key, value, spider=None):
            self.track_duplicate_stat_calls(key)
            super().max_value(key, value, spider)

        def min_value(self, key, value, spider=None):
            self.track_duplicate_stat_calls(key)
            super().min_value(key, value, spider)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            for url in (
                mockserver.urljoin("/products/a"),
                mockserver.urljoin("/products/b"),
            ):
                yield Request(url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["STATS_CLASS"] = OnlyOnceStatsCollector
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(TestSpider, HtmlResource, settings)

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/zyte_common_items.items.product.Product": (
            "(all fields)"
        ),
    }
    assert all(value == 0 for value in duplicate_stat_calls.values())


@ensureDeferred
async def test_partial_override(mockserver):
    """When requesting an item and having an Auto…Page subclass to change
    fields, stats reflect the list of item fields not defined in the
    subclass. Defined field methods are not listed, even if they return the
    original item field, directly or as a fallback."""

    class MyProductPage(AutoProductPage):

        @field
        def brand(self):
            return "foo"

        @field
        def name(self):
            return self.product.name

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_partial_override.<locals>.MyProductPage": (
            "additionalProperties aggregateRating availability breadcrumbs "
            "canonicalUrl color currency currencyRaw description descriptionHtml "
            "features gtin images mainImage metadata mpn price productId "
            "regularPrice size sku style url variants"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_full_override(mockserver):
    """When requesting an item and having an Auto…Page subclass to change
    all fields, stats reflect the list of non-overriden item fields as an empty
    string."""

    # Copy-paste of fields from the AutoProductPage implementation, with type
    # hints removed.
    class MyProductPage(AutoProductPage):

        @field
        def additionalProperties(self):
            return self.product.additionalProperties

        @field
        def aggregateRating(self):
            return self.product.aggregateRating

        @field
        def availability(self):
            return self.product.availability

        @field
        def brand(self):
            return self.product.brand

        @field
        def breadcrumbs(self):
            return self.product.breadcrumbs

        @field
        def canonicalUrl(self):
            return self.product.canonicalUrl

        @field
        def color(self):
            return self.product.color

        @field
        def currency(self):
            return self.product.currency

        @field
        def currencyRaw(self):
            return self.product.currencyRaw

        @field
        def description(self):
            return self.product.description

        @field
        def descriptionHtml(self):
            return self.product.descriptionHtml

        @field
        def features(self):
            return self.product.features

        @field
        def gtin(self):
            return self.product.gtin

        @field
        def images(self):
            return self.product.images

        @field
        def mainImage(self):
            return self.product.mainImage

        @field
        def metadata(self):
            return self.product.metadata

        @field
        def mpn(self):
            return self.product.mpn

        @field
        def name(self):
            return self.product.name

        @field
        def price(self):
            return self.product.price

        @field
        def productId(self):
            return self.product.productId

        @field
        def regularPrice(self):
            return self.product.regularPrice

        @field
        def size(self):
            return self.product.size

        @field
        def sku(self):
            return self.product.sku

        @field
        def style(self):
            return self.product.style

        @field
        def url(self):
            return self.product.url

        @field
        def variants(self):
            return self.product.variants

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_full_override.<locals>.MyProductPage": "",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_callback_override(mockserver):
    """Fields overridden in callbacks, instead of using a page object, are not
    taken into account."""

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            product.name = "foo"
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/zyte_common_items.items.product.Product": (
            "(all fields)"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_item_page_override(mockserver):
    """The stat accounts for the configured page for a given item, so if you
    request that page directly, things work the same as if you request the item
    itself."""

    class MyProductPage(AutoProductPage):

        @field
        def brand(self):
            return "foo"

        @field
        def name(self):
            return self.product.name

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        async def parse(self, response: DummyResponse, page: MyProductPage):
            yield await page.to_item()

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_item_page_override.<locals>.MyProductPage": (
            "additionalProperties aggregateRating availability breadcrumbs "
            "canonicalUrl color currency currencyRaw description descriptionHtml "
            "features gtin images mainImage metadata mpn price productId "
            "regularPrice size sku style url variants"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_alt_page_override(mockserver):
    """The stat does not account for alternatives pages, so if you request a
    page that provides an item, the page that counts for stats is the
    configured page for that item, not the actual page requested."""

    class MyProductPage(AutoProductPage):

        @field
        def brand(self):
            return "foo"

        @field
        def name(self):
            return self.product.name

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class AltProductPage(AutoProductPage):

        @field
        def sku(self):
            return "foo"

        @field
        def currencyRaw(self):
            return self.product.currencyRaw

    handle_urls(f"{mockserver.host}:{mockserver.port}", priority=0)(AltProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        async def parse(self, response: DummyResponse, page: AltProductPage):
            yield await page.to_item()

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_alt_page_override.<locals>.MyProductPage": (
            "additionalProperties aggregateRating availability breadcrumbs "
            "canonicalUrl color currency currencyRaw description descriptionHtml "
            "features gtin images mainImage metadata mpn price productId "
            "regularPrice size sku style url variants"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_non_auto_override(mockserver):
    """If instead of using an Auto…Page class you use a custom class, all
    fields are assumed to be overridden."""

    @attrs.define
    class MyProductPage(BaseProductPage):
        product: Product

        @field
        def additionalProperties(self):
            return self.product.additionalProperties

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_non_auto_override.<locals>.MyProductPage": "",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_decorator(mockserver):
    """Using @auto_field forces a field to not be considered overridden."""

    @attrs.define
    class MyProductPage(BaseProductPage):
        product: Product

        @auto_field
        def additionalProperties(self):
            return self.product.additionalProperties

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_auto_field_decorator.<locals>.MyProductPage": "additionalProperties",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_meta(mockserver):
    """Using @field(meta={"auto_field": True}) has the same effect as using
    @auto_field."""

    @attrs.define
    class MyProductPage(BaseProductPage):
        product: Product

        @field(meta={"auto_field": True})
        def additionalProperties(self):
            return self.product.additionalProperties

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_auto_field_meta.<locals>.MyProductPage": "additionalProperties",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_custom_item(mockserver):
    server = f"{mockserver.host}:{mockserver.port}"
    url = f"http://{server}/"

    @attrs.define
    class CustomProduct(Item):
        url: str
        product_title: Optional[str] = None

    @attrs.define
    class MyProductPage(ItemPage[CustomProduct]):
        product: Product

        @field
        def url(self) -> str:
            return url

        @field(meta={"auto_field": True})
        def product_title(self) -> Optional[str]:
            return self.product.name

    handle_urls(server)(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: CustomProduct):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_custom_item.<locals>.MyProductPage": "product_title",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_custom_item_missing_url(mockserver, caplog):
    @attrs.define
    class CustomProduct(Item):
        weight: Optional[float] = None
        product_title: Optional[str] = None

    @attrs.define
    class MyProductPage(ItemPage[CustomProduct]):
        product: Product

        @field
        def weight(self) -> Optional[float]:
            return None

        @field(meta={"auto_field": True})
        def product_title(self) -> Optional[str]:
            return self.product.name

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: CustomProduct):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    caplog.clear()
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {}

    assert len(caplog.records) == 1
    assert "was missing a non-empty URL" in caplog.records[0].msg

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_custom_item_custom_url_field(mockserver):
    @attrs.define
    class CustomProduct(Item):
        product_url: str
        product_title: Optional[str] = None

    @attrs.define
    class MyProductPage(ItemPage[CustomProduct]):
        product: Product

        @field(meta={"auto_field": True})
        def product_url(self) -> str:
            return self.product.url

        @field(meta={"auto_field": True})
        def product_title(self) -> Optional[str]:
            return self.product.name

    handle_urls(f"{mockserver.host}:{mockserver.port}")(MyProductPage)

    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: CustomProduct):
            yield product

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ITEM_PIPELINES"]["scrapy_zyte_api.poet.ScrapyZyteAPIPoetItemPipeline"] = 0
    settings["ZYTE_API_AUTO_FIELD_STATS"] = True
    settings["ZYTE_API_AUTO_FIELD_URL_FIELDS"] = {CustomProduct: "product_url"}
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(
        TestSpider, HtmlResource, settings, port=mockserver.port
    )

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {
        "scrapy-zyte-api/auto_fields/tests.test_auto_field_stats.test_custom_item_custom_url_field.<locals>.MyProductPage": "(all fields)",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]
