import attrs
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy_poet import DummyResponse
from scrapy_poet.utils.testing import (
    HtmlResource,
    crawl_single_item,
    create_scrapy_settings,
)
from web_poet import BrowserResponse
from zyte_common_items import BasePage, Product

from scrapy_zyte_api.providers import ZyteApiProvider

from . import SETTINGS


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
