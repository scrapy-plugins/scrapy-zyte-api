from collections import defaultdict
from typing import Annotated

import pytest

pytest.importorskip("scrapy_poet")

import attrs
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy_poet import DummyResponse
from scrapy_poet.utils.testing import HtmlResource, crawl_single_item
from scrapy_poet.utils.testing import create_scrapy_settings as _create_scrapy_settings
from twisted.internet import reactor
from twisted.web.client import Agent, readBody
from web_poet import (
    AnyResponse,
    BrowserHtml,
    BrowserResponse,
    HttpResponse,
    ItemPage,
    default_registry,
    field,
    handle_urls,
)
from web_poet.pages import get_item_cls
from zyte_common_items import (
    AutoProductPage,
    BasePage,
    BaseProductPage,
    CustomAttributes,
    CustomAttributesValues,
    Product,
    ProductNavigation,
)
from zyte_common_items.fields import auto_field

from scrapy_zyte_api import (
    Actions,
    ExtractFrom,
    Geolocation,
    Screenshot,
    actions,
    custom_attrs,
)
from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler
from scrapy_zyte_api.providers import _AUTO_PAGES, _ITEM_KEYWORDS, ZyteApiProvider

from . import SETTINGS
from .mockserver import get_ephemeral_port

PROVIDER_PARAMS = {"geolocation": "IE"}


def create_scrapy_settings():
    settings = _create_scrapy_settings()
    for setting, value in SETTINGS.items():
        if setting.endswith("_MIDDLEWARES") and settings[setting]:
            settings[setting].update(value)
        else:
            settings[setting] = value
    return settings


@attrs.define
class ProductPage(BasePage):
    html: BrowserHtml
    response: BrowserResponse
    product: Product


@attrs.define
class ProductNavigationPage(BasePage):
    html: BrowserHtml
    response: BrowserResponse
    product_nav: ProductNavigation


class ZyteAPISpider(Spider):
    url: str

    def start_requests(self):
        yield Request(self.url, callback=self.parse_)

    def parse_(self, response: DummyResponse, page: ProductPage):
        yield {
            "html": page.html,
            "response_html": page.response.html,
            "product": page.product,
        }


class ZyteAPIProviderMetaSpider(Spider):
    url: str

    def start_requests(self):
        yield Request(
            self.url, callback=self.parse_, meta={"zyte_api_provider": PROVIDER_PARAMS}
        )

    def parse_(self, response: DummyResponse, page: ProductPage):
        yield {
            "html": page.html,
            "response_html": page.response.html,
            "product": page.product,
        }


@ensureDeferred
async def test_provider(mockserver):
    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    item, url, _ = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    assert item["html"] == "<html><body>Hello<h1>World!</h1></body></html>"
    assert item["response_html"] == "<html><body>Hello<h1>World!</h1></body></html>"
    assert item["product"] == Product.from_dict(
        dict(
            url=url,
            name="Product name",
            price="10",
            currency="USD",
        )
    )


@attrs.define
class MyItem:
    url: str


@attrs.define
class MyPage(ItemPage[MyItem]):
    response: BrowserResponse

    @field
    def url(self) -> str:
        return str(self.response.url)


@ensureDeferred
async def test_itemprovider_requests_direct_dependencies(fresh_mockserver):
    class ItemDepSpider(ZyteAPISpider):
        def parse_(  # type: ignore[override]
            self,
            response: DummyResponse,
            browser_response: BrowserResponse,
            product: Product,
        ):
            yield {
                "product": product,
                "browser_response": browser_response,
            }

    port = get_ephemeral_port()
    handle_urls(f"{fresh_mockserver.host}:{port}")(MyPage)

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = fresh_mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 1100}
    item, url, _ = await crawl_single_item(
        ItemDepSpider, HtmlResource, settings, port=port
    )
    count_resp = await Agent(reactor).request(
        b"GET", fresh_mockserver.urljoin("/count").encode()
    )
    call_count = int((await readBody(count_resp)).decode())
    assert call_count == 1
    assert "browser_response" in item
    assert "product" in item


@ensureDeferred
async def test_itemprovider_requests_indirect_dependencies(fresh_mockserver):
    class ItemDepSpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, product: Product, my_item: MyItem):  # type: ignore[override]
            yield {
                "product": product,
                "my_item": my_item,
            }

    port = get_ephemeral_port()
    handle_urls(f"{fresh_mockserver.host}:{port}")(MyPage)

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = fresh_mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 1100}
    item, url, _ = await crawl_single_item(
        ItemDepSpider, HtmlResource, settings, port=port
    )
    count_resp = await Agent(reactor).request(
        b"GET", fresh_mockserver.urljoin("/count").encode()
    )
    call_count = int((await readBody(count_resp)).decode())
    assert call_count == 1
    assert "my_item" in item
    assert "product" in item


@ensureDeferred
async def test_itemprovider_requests_indirect_dependencies_workaround(fresh_mockserver):
    class ItemDepSpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, product: Product, browser_response: BrowserResponse, my_item: MyItem):  # type: ignore[override]
            yield {
                "product": product,
                "my_item": my_item,
                "browser_response": browser_response,
            }

    port = get_ephemeral_port()
    handle_urls(f"{fresh_mockserver.host}:{port}")(MyPage)

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = fresh_mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 1}
    item, url, _ = await crawl_single_item(
        ItemDepSpider, HtmlResource, settings, port=port
    )
    count_resp = await Agent(reactor).request(
        b"GET", fresh_mockserver.urljoin("/count").encode()
    )
    call_count = int((await readBody(count_resp)).decode())
    assert call_count == 1
    assert "my_item" in item
    assert "product" in item
    assert "browser_response" in item


@ensureDeferred
async def test_provider_params_setting(mockserver):
    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ZYTE_API_PROVIDER_PARAMS"] = PROVIDER_PARAMS
    _, _, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    assert crawler.stats.get_value("scrapy-zyte-api/request_args/browserHtml") == 1
    assert crawler.stats.get_value("scrapy-zyte-api/request_args/geolocation") == 1


@ensureDeferred
async def test_provider_params_meta(mockserver):
    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    _, _, crawler = await crawl_single_item(
        ZyteAPIProviderMetaSpider, HtmlResource, settings
    )
    assert crawler.stats.get_value("scrapy-zyte-api/request_args/browserHtml") == 1
    assert crawler.stats.get_value("scrapy-zyte-api/request_args/geolocation") == 1


@ensureDeferred
async def test_provider_params_remove_unused_options(mockserver):
    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ZYTE_API_PROVIDER_PARAMS"] = {
        "productOptions": {"extractFrom": "httpResponseBody"},
        "productNavigationOptions": {"extractFrom": "httpResponseBody"},
    }
    _, _, crawler = await crawl_single_item(ZyteAPISpider, Product, settings)
    assert crawler.stats.get_value("scrapy-zyte-api/request_args/product") == 1
    assert crawler.stats.get_value("scrapy-zyte-api/request_args/productOptions") == 1
    assert (
        crawler.stats.get_value("scrapy-zyte-api/request_args/productNavigationOptions")
        is None
    )


@ensureDeferred
async def test_provider_extractfrom(mockserver):
    @attrs.define
    class AnnotatedProductPage(BasePage):
        product: Annotated[Product, ExtractFrom.httpResponseBody]
        product2: Annotated[Product, ExtractFrom.httpResponseBody]

    class AnnotatedZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: AnnotatedProductPage):  # type: ignore[override]
            yield {
                "product": page.product,
                "product2": page.product,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, url, _ = await crawl_single_item(
        AnnotatedZyteAPISpider, HtmlResource, settings
    )
    assert item["product"] == Product.from_dict(
        dict(
            url=url,
            name="Product name (from httpResponseBody)",
            price="10",
            currency="USD",
        )
    )


@ensureDeferred
async def test_provider_extractfrom_double(mockserver, caplog):
    @attrs.define
    class AnnotatedProductPage(BasePage):
        product: Annotated[Product, ExtractFrom.httpResponseBody]
        product2: Annotated[Product, ExtractFrom.browserHtml]

    class AnnotatedZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: AnnotatedProductPage):  # type: ignore[override]
            yield {
                "product": page.product,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, _, _ = await crawl_single_item(AnnotatedZyteAPISpider, HtmlResource, settings)
    assert item is None
    assert "Multiple different extractFrom specified for product" in caplog.text


@ensureDeferred
async def test_provider_extractfrom_override(mockserver):
    @attrs.define
    class AnnotatedProductPage(BasePage):
        product: Annotated[Product, ExtractFrom.httpResponseBody]

    class AnnotatedZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: AnnotatedProductPage):  # type: ignore[override]
            yield {
                "product": page.product,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ZYTE_API_PROVIDER_PARAMS"] = {
        "productOptions": {"extractFrom": "browserHtml"}
    }

    item, url, _ = await crawl_single_item(
        AnnotatedZyteAPISpider, HtmlResource, settings
    )
    assert item["product"] == Product.from_dict(
        dict(
            url=url,
            name="Product name",
            price="10",
            currency="USD",
        )
    )


@ensureDeferred
async def test_provider_geolocation(mockserver):
    @attrs.define
    class GeoProductPage(BasePage):
        product: Product
        geolocation: Annotated[Geolocation, "DE"]

    class GeoZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: GeoProductPage):  # type: ignore[override]
            yield {
                "product": page.product,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, url, _ = await crawl_single_item(GeoZyteAPISpider, HtmlResource, settings)
    assert item["product"].name == "Product name (country DE)"


@ensureDeferred
async def test_provider_geolocation_unannotated(mockserver, caplog):
    @attrs.define
    class GeoProductPage(BasePage):
        product: Product
        geolocation: Geolocation

    class GeoZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: GeoProductPage):  # type: ignore[override]
            pass

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, url, _ = await crawl_single_item(GeoZyteAPISpider, HtmlResource, settings)
    assert item is None
    assert "Geolocation dependencies must be annotated" in caplog.text


custom_attrs_input = {
    "attr1": {"type": "string", "description": "descr1"},
    "attr2": {"type": "number", "description": "descr2"},
}


@pytest.mark.parametrize(
    "annotation",
    [
        custom_attrs(custom_attrs_input),
        custom_attrs(custom_attrs_input, None),
        custom_attrs(custom_attrs_input, {}),
        custom_attrs(custom_attrs_input, {"foo": "bar"}),
    ],
)
@ensureDeferred
async def test_provider_custom_attrs(mockserver, annotation):
    @attrs.define
    class CustomAttrsPage(BasePage):
        product: Product
        custom_attrs: Annotated[CustomAttributes, annotation]

    class CustomAttrsZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: CustomAttrsPage):  # type: ignore[override]
            yield {
                "product": page.product,
                "custom_attrs": page.custom_attrs,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, url, _ = await crawl_single_item(
        CustomAttrsZyteAPISpider, HtmlResource, settings
    )
    assert item["product"] == Product.from_dict(
        dict(
            url=url,
            name="Product name",
            price="10",
            currency="USD",
        )
    )
    assert item["custom_attrs"] == CustomAttributes.from_dict(
        {
            "values": {
                "attr1": "foo",
                "attr2": 42,
            },
            "metadata": {"textInputTokens": 1000},
        }
    )


@ensureDeferred
async def test_provider_custom_attrs_values(mockserver):
    @attrs.define
    class CustomAttrsPage(BasePage):
        product: Product
        custom_attrs: Annotated[
            CustomAttributesValues,
            custom_attrs(custom_attrs_input),
        ]

    class CustomAttrsZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: CustomAttrsPage):  # type: ignore[override]
            yield {
                "product": page.product,
                "custom_attrs": page.custom_attrs,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, url, _ = await crawl_single_item(
        CustomAttrsZyteAPISpider, HtmlResource, settings
    )
    assert item["product"] == Product.from_dict(
        dict(
            url=url,
            name="Product name",
            price="10",
            currency="USD",
        )
    )
    assert item["custom_attrs"] == {
        "attr1": "foo",
        "attr2": 42,
    }


class RecordingHandler(ScrapyZyteAPIDownloadHandler):
    """Subclasses the original handler in order to record the Zyte API parameters
    used for each downloading request.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params = []

    def _log_request(self, params):
        self.params.append(params)


def provider_settings(server):
    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = server.urljoin("/")
    settings["ZYTE_API_TRANSPARENT_MODE"] = True
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 1100}
    settings["DOWNLOAD_HANDLERS"]["http"] = RecordingHandler
    return settings


@ensureDeferred
async def test_provider_any_response_only(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
    }
    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is HttpResponse


@ensureDeferred
async def test_provider_any_response_http_response_param(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"httpResponseBody": True}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
    }
    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is HttpResponse


@ensureDeferred
async def test_provider_any_response_browser_html_param(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"browserHtml": True}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "browserHtml": True,
    }
    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse


@ensureDeferred
async def test_provider_any_response_product(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        product: Product

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "browserHtml": True,
    }
    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].product) is Product


@ensureDeferred
async def test_provider_any_response_product_extract_from_browser_html(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        product: Product

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    product_options = {"extractFrom": "browserHtml"}
    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"productOptions": product_options}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "browserHtml": True,
        "productOptions": product_options,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].product) is Product


@ensureDeferred
async def test_provider_any_response_product_item_extract_from_browser_html(mockserver):
    @attrs.define
    class SomePage(ItemPage[Product]):
        response: AnyResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage, product: Product):
            yield {"page": page, "product": product}

    product_options = {"extractFrom": "browserHtml"}
    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"productOptions": product_options}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "browserHtml": True,
        "productOptions": product_options,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["product"]) is Product


@ensureDeferred
async def test_provider_any_response_product_extract_from_browser_html_2(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        browser_response: BrowserResponse
        product: Product

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    product_options = {"extractFrom": "browserHtml"}
    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"productOptions": product_options}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "browserHtml": True,
        "productOptions": product_options,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].browser_response) is BrowserResponse
    assert type(item["page"].product) is Product

    assert id(item["page"].browser_response) == id(item["page"].response.response)


@ensureDeferred
async def test_provider_any_response_product_extract_from_http_response(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        product: Product

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    product_options = {"extractFrom": "httpResponseBody"}
    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"productOptions": product_options}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "httpResponseBody": True,
        "productOptions": product_options,
        "httpResponseHeaders": True,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is HttpResponse
    assert type(item["page"].product) is Product


@ensureDeferred
async def test_provider_any_response_product_options_empty(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        product: Product

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"productOptions": {}}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "browserHtml": True,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].product) is Product


# The issue here is that HttpResponseProvider runs earlier than ScrapyZyteAPI.
# HttpResponseProvider doesn't know that it should not run since ScrapyZyteAPI
# could provide HttpResponse in anycase.
@pytest.mark.xfail(reason="Not supported yet", raises=AssertionError, strict=True)
@ensureDeferred
async def test_provider_any_response_product_extract_from_http_response_2(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        http_response: HttpResponse
        product: Product

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    product_options = {"extractFrom": "httpResponseBody"}
    settings = provider_settings(mockserver)
    settings["ZYTE_API_PROVIDER_PARAMS"] = {"productOptions": product_options}
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "product": True,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
        "productOptions": product_options,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is HttpResponse
    assert type(item["page"].product) is Product
    assert type(item["page"].http_response) is HttpResponse


@ensureDeferred
async def test_provider_any_response_browser_html(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        html: BrowserHtml

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {"url": url, "browserHtml": True}

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].html) is BrowserHtml


@ensureDeferred
async def test_provider_any_response_browser_response(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        browser_response: BrowserResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {"url": url, "browserHtml": True}

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].browser_response) is BrowserResponse


@ensureDeferred
async def test_provider_any_response_browser_html_response(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        browser_response: BrowserResponse
        html: BrowserHtml

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {"url": url, "browserHtml": True}

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].browser_response) is BrowserResponse
    assert type(item["page"].html) is BrowserHtml


@ensureDeferred
async def test_provider_any_response_http_response(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        http_response: HttpResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
    }

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is HttpResponse
    assert type(item["page"].http_response) is HttpResponse


@ensureDeferred
async def test_provider_any_response_browser_http_response(mockserver):
    @attrs.define
    class SomePage(BasePage):
        response: AnyResponse
        browser_response: BrowserResponse
        http_response: HttpResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page: SomePage):
            yield {"page": page}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 2
    assert params[0] == {
        "url": url,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
    }
    assert params[1] == {"url": url, "browserHtml": True}

    assert type(item["page"].response) is AnyResponse
    assert type(item["page"].response.response) is BrowserResponse
    assert type(item["page"].browser_response) is BrowserResponse
    assert type(item["page"].http_response) is HttpResponse

    assert id(item["page"].browser_response) == id(item["page"].response.response)


@ensureDeferred
async def test_provider_any_response_http_response_multiple_pages(mockserver):
    @attrs.define
    class FirstPage(BasePage):
        http_response: HttpResponse

    @attrs.define
    class SecondPage(BasePage):
        http_response: HttpResponse
        response: AnyResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page1: FirstPage, page2: SecondPage):
            yield {"page1": page1, "page2": page2}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {
        "url": url,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
    }
    assert type(item["page1"].http_response) is HttpResponse
    assert type(item["page2"].http_response) is HttpResponse
    assert type(item["page2"].response) is AnyResponse
    assert type(item["page2"].response.response) is HttpResponse


@ensureDeferred
async def test_provider_any_response_http_browser_response_multiple_pages(mockserver):
    @attrs.define
    class FirstPage(BasePage):
        browser_response: BrowserResponse

    @attrs.define
    class SecondPage(BasePage):
        http_response: HttpResponse
        response: AnyResponse

    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, page1: FirstPage, page2: SecondPage):
            yield {"page1": page1, "page2": page2}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 2
    assert params[0] == {
        "url": url,
        "httpResponseBody": True,
        "httpResponseHeaders": True,
    }
    assert params[1] == {"url": url, "browserHtml": True}

    assert type(item["page1"].browser_response) is BrowserResponse
    assert type(item["page2"].http_response) is HttpResponse
    assert type(item["page2"].response) is AnyResponse
    assert type(item["page2"].response.response) is BrowserResponse


@ensureDeferred
async def test_screenshot(mockserver):
    class ZyteAPISpider(Spider):
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse_)

        def parse_(self, response: DummyResponse, screenshot: Screenshot):
            yield {"screenshot": screenshot}

    settings = provider_settings(mockserver)
    item, url, crawler = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    params = crawler.engine.downloader.handlers._handlers["http"].params

    assert len(params) == 1
    assert params[0] == {"url": url, "screenshot": True}

    assert type(item["screenshot"]) is Screenshot
    assert item["screenshot"].body == b"screenshot-body-contents"


@ensureDeferred
async def test_provider_actions(mockserver, caplog):
    @attrs.define
    class ActionProductPage(BasePage):
        product: Product
        actions: Annotated[
            Actions,
            actions(
                [
                    {
                        "action": "foo",
                        "selector": {"type": "css", "value": "button#openDescription"},
                    },
                    {"action": "bar"},
                ]
            ),
        ]

    class ActionZyteAPISpider(ZyteAPISpider):
        def parse_(self, response: DummyResponse, page: ActionProductPage):  # type: ignore[override]
            yield {
                "product": page.product,
                "action_results": page.actions,
            }

    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}

    item, url, _ = await crawl_single_item(ActionZyteAPISpider, HtmlResource, settings)
    assert isinstance(item["product"], Product)
    assert item["action_results"] == Actions(
        [
            {
                "action": "foo",
                "elapsedTime": 1.0,
                "status": "success",
            },
            {
                "action": "bar",
                "elapsedTime": 1.0,
                "status": "success",
            },
        ]
    )


def test_auto_pages_set():
    assert set(_ITEM_KEYWORDS) == {get_item_cls(cls) for cls in _AUTO_PAGES}  # type: ignore[call-overload]


@ensureDeferred
async def test_auto_field_stats_not_enabled(mockserver):
    class TestSpider(Spider):
        name = "test_spider"
        url: str

        def start_requests(self):
            yield Request(self.url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    _, _, crawler = await crawl_single_item(TestSpider, HtmlResource, settings)

    auto_field_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/auto_fields")
    }
    assert auto_field_stats == {}


@ensureDeferred
async def test_auto_field_stats_no_override(mockserver):
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
            for url in ("data:,a", "data:,b"):
                yield Request(url, callback=self.parse)

        def parse(self, response: DummyResponse, product: Product):
            pass

    settings = create_scrapy_settings()
    settings["STATS_CLASS"] = OnlyOnceStatsCollector
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
async def test_auto_field_stats_partial_override(mockserver):
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
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_partial_override.<locals>.MyProductPage": (
            "additionalProperties aggregateRating availability breadcrumbs "
            "canonicalUrl color currency currencyRaw description descriptionHtml "
            "features gtin images mainImage metadata mpn price productId "
            "regularPrice size sku style url variants"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_stats_full_override(mockserver):
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
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_full_override.<locals>.MyProductPage": "",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_stats_callback_override(mockserver):
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
async def test_auto_field_stats_item_page_override(mockserver):
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

        def parse(self, response: DummyResponse, page: MyProductPage):
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_item_page_override.<locals>.MyProductPage": (
            "additionalProperties aggregateRating availability breadcrumbs "
            "canonicalUrl color currency currencyRaw description descriptionHtml "
            "features gtin images mainImage metadata mpn price productId "
            "regularPrice size sku style url variants"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_stats_alt_page_override(mockserver):
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

        def parse(self, response: DummyResponse, page: AltProductPage):
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_alt_page_override.<locals>.MyProductPage": (
            "additionalProperties aggregateRating availability breadcrumbs "
            "canonicalUrl color currency currencyRaw description descriptionHtml "
            "features gtin images mainImage metadata mpn price productId "
            "regularPrice size sku style url variants"
        ),
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_stats_non_auto_override(mockserver):
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
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_non_auto_override.<locals>.MyProductPage": "",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_stats_auto_field_decorator(mockserver):
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
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_auto_field_decorator.<locals>.MyProductPage": "additionalProperties",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


@ensureDeferred
async def test_auto_field_stats_auto_field_meta(mockserver):
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
            pass

    settings = create_scrapy_settings()
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
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
        "scrapy-zyte-api/auto_fields/tests.test_providers.test_auto_field_stats_auto_field_meta.<locals>.MyProductPage": "additionalProperties",
    }

    # Reset rules
    default_registry.__init__()  # type: ignore[misc]


class ZyteAPIMultipleSpider(Spider):
    url: str

    def start_requests(self):
        yield Request(self.url, callback=self.parse_)

    def parse_(
        self,
        response: DummyResponse,
        page: ProductPage,
        nav_page: ProductNavigationPage,
    ):
        yield {
            "html": page.html,
            "response_html": page.response.html,
            "product": page.product,
            "productNavigation": nav_page.product_nav,
        }


@ensureDeferred
async def test_multiple_types(mockserver):
    settings = create_scrapy_settings()
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    item, url, _ = await crawl_single_item(
        ZyteAPIMultipleSpider, HtmlResource, settings
    )
    assert item["html"] == "<html><body>Hello<h1>World!</h1></body></html>"
    assert item["response_html"] == "<html><body>Hello<h1>World!</h1></body></html>"
    assert item["product"] == Product.from_dict(
        dict(
            url=url,
            name="Product name",
            price="10",
            currency="USD",
        )
    )
    assert item["productNavigation"] == ProductNavigation.from_dict(
        dict(
            url=url,
            name="Product navigation",
            pageNumber=0,
        )
    )
