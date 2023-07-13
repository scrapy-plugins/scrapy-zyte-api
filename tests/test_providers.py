import attrs
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
from web_poet import BrowserHtml, BrowserResponse, ItemPage, field, handle_urls
from zyte_common_items import BasePage, Product

from scrapy_zyte_api.providers import ZyteApiProvider

from . import SETTINGS
from .mockserver import get_ephemeral_port


@attrs.define
class ProductPage(BasePage):
    html: BrowserHtml
    response: BrowserResponse
    product: Product


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


@ensureDeferred
async def test_provider(mockserver):
    settings = create_scrapy_settings(None)
    settings.update(SETTINGS)
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

    settings = create_scrapy_settings(None)
    settings.update(SETTINGS)
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
        def parse_(self, response: DummyResponse, product: Product, my_page: MyPage):  # type: ignore[override]
            yield {
                "product": product,
                "my_page": my_page,
            }

    port = get_ephemeral_port()
    handle_urls(f"{fresh_mockserver.host}:{port}")(MyPage)

    settings = create_scrapy_settings(None)
    settings.update(SETTINGS)
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
    assert "my_page" in item
    assert "product" in item


# TODO: Make incremental changes to this test to make it closer to the test
# above until you find what makes the test below pass while the test above
# fails.
@ensureDeferred
async def test_build_callback_dependencies_minimize_provider_calls():
    import attr
    from scrapy_poet import PageObjectInputProvider
    from scrapy_poet.injection import get_injector_for_testing, get_response_for_testing
    from scrapy_poet.page_input_providers import ItemProvider
    from web_poet import ApplyRule, Injectable

    class ExpensiveDependency1:
        pass

    class ExpensiveDependency2:
        pass

    class ExpensiveProvider(PageObjectInputProvider):
        provided_classes = {ExpensiveDependency1, ExpensiveDependency2}

        def __call__(self, to_provide):
            if to_provide != self.provided_classes:
                raise RuntimeError(
                    "The expensive dependency provider has been called "
                    "with a subset of the classes that it provides and "
                    "that are required for the callback in this test."
                )
            return [cls() for cls in to_provide]

    @attrs.define
    class MyItem:
        pass

    @attrs.define
    class MyPage(ItemPage[MyItem]):
        expensive: ExpensiveDependency2

    def callback(
        expensive: ExpensiveDependency1,
        item: MyItem,
    ):
        pass

    providers = {
        ItemProvider: 1,
        ExpensiveProvider: 2,
    }
    injector = get_injector_for_testing(providers)
    injector.registry.add_rule(ApplyRule("", use=MyPage, to_return=MyItem))
    response = get_response_for_testing(callback)

    # This would raise RuntimeError if expectations are not met.
    kwargs = await injector.build_callback_dependencies(response.request, response)

    # Make sure the test does not simply pass because some dependencies were
    # not injected at all.
    assert set(kwargs.keys()) == {"expensive", "item"}


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

    settings = create_scrapy_settings(None)
    settings.update(SETTINGS)
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
