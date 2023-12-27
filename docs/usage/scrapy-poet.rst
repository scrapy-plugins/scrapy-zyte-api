.. _scrapy-poet:

=======================
scrapy-poet integration
=======================

After you :ref:`set up scrapy-poet integration <scrapy-poet-setup>`, you can
request :ref:`supported page inputs <inputs>` in your page objects::

    @attrs.define
    class ProductPage(BasePage):
        response: BrowserResponse
        product: Product


    class ZyteApiSpider(scrapy.Spider):
        ...

        def parse_page(self, response: DummyResponse, page: ProductPage):
            ...

Or request them directly in the callback::

    class ZyteApiSpider(scrapy.Spider):
        ...

        def parse_page(self,
                       response: DummyResponse,
                       browser_response: BrowserResponse,
                       product: Product,
                       ):
            ...

Default parameters
==================

scrapy-poet integration ignores :ref:`default parameters <default>`.

To add extra parameters to all Zyte API requests sent by the provider, set them
as a dictionary through the :ref:`ZYTE_API_PROVIDER_PARAMS` setting, for
example in ``settings.py``::

    ZYTE_API_PROVIDER_PARAMS = {"geolocation": "IE"}

When :ref:`ZYTE_API_PROVIDER_PARAMS` includes one of the Zyte API extraction
options (e.g. ``productOptions`` for ``product``), but the final Zyte API
request doesn't include the corresponding data type, the unused options are
automatically removed. So, it's safe to use :ref:`ZYTE_API_PROVIDER_PARAMS` to
set the default options for various extraction types, e.g.::

    ZYTE_API_PROVIDER_PARAMS = {
        "productOptions": {"extractFrom": "httpResponseBody"},
        "productNavigationOptions": {"extractFrom": "httpResponseBody"},
    }

Note that the built-in ``scrapy_poet.page_input_providers.ItemProvider`` has a
priority of 2000, so when you have page objects producing
:class:`zyte_common_items.Product` items you should use higher values for
``ZyteApiProvider`` if you want these items to come from these page objects,
and lower values if you want them to come from Zyte API.

Currently, when ``ItemProvider`` is used together with ``ZyteApiProvider``,
it may make more requests than is optimal: the normal Scrapy response will be
always requested even when using a :class:`~scrapy_poet.DummyResponse`
annotation, and in some dependency combinations two Zyte API requests will be
made for the same page. We are planning to solve these problems in the future
releases of :doc:`scrapy-poet <scrapy-poet:index>` and scrapy-zyte-api.


Dependency annotations
======================

``ZyteApiProvider`` understands some dependency annotations. The only currently
supported one is :class:`scrapy_zyte_api.ExtractFrom`:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import ExtractFrom

    @attrs.define
    class MyPageObject(BasePage):
        product: Annotated[Product, ExtractFrom.httpResponseBody]

The provider will set the extraction options based on the annotations, so for
this code ``extractFrom`` will be set to ``httpResponseBody`` in
``productOptions``.
