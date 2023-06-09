import attrs
import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy_poet import DummyResponse
from scrapy_poet.utils.testing import (
    HtmlResource,
    crawl_single_item,
    create_scrapy_settings,
)
from twisted.internet import reactor
from twisted.web.client import Agent, readBody
from web_poet import BrowserResponse, ItemPage, field, handle_urls
from zyte_common_items import BasePage, Product

from scrapy_zyte_api.providers import ZyteApiProvider

from . import SETTINGS
from .mockserver import get_ephemeral_port


@attrs.define
class ProductPage(BasePage):
    response: BrowserResponse
    product: Product


class ZyteAPISpider(Spider):
    url: str

    def start_requests(self):
        yield Request(self.url, callback=self.parse_)

    def parse_(self, response: DummyResponse, page: ProductPage):
        yield {
            "html": page.response.html,
            "product": page.product,
        }


@ensureDeferred
async def test_provider(mockserver):
    settings = create_scrapy_settings(None)
    settings.update(SETTINGS)
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 0}
    item, url, _ = await crawl_single_item(ZyteAPISpider, HtmlResource, settings)
    assert item["html"] == "<html><body>Hello<h1>World!</h1></body></html>"
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


class ItemDepSpider(ZyteAPISpider):
    def parse_(self, response: DummyResponse, product: Product, my_item: MyItem):  # type: ignore[override]
        yield {
            "product": product,
            "my_item": my_item,
        }


@pytest.mark.xfail(reason="Not implemented yet", raises=AssertionError, strict=True)
@ensureDeferred
async def test_itemprovider_requests(mockserver):
    port = get_ephemeral_port()
    handle_urls(f"{mockserver.host}:{port}")(MyPage)

    settings = create_scrapy_settings(None)
    settings.update(SETTINGS)
    settings["ZYTE_API_URL"] = mockserver.urljoin("/")
    settings["SCRAPY_POET_PROVIDERS"] = {ZyteApiProvider: 1100}
    item, url, _ = await crawl_single_item(
        ItemDepSpider, HtmlResource, settings, port=port
    )
    count_resp = await Agent(reactor).request(
        b"GET", mockserver.urljoin("/count").encode()
    )
    call_count = int((await readBody(count_resp)).decode())
    assert call_count == 1
    assert "my_item" in item
    assert "product" in item
