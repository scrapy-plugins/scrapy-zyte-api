.. _scrapy-poet:

=======================
scrapy-poet integration
=======================

If during the :ref:`initial setup <setup>` you followed the required steps for
scrapy-poet integration, you can request :ref:`supported page inputs <inputs>`
in your page objects::

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

.. note:: Dependency annotations require Python 3.9+.

Geolocation
===========

You can specify the geolocation field by adding a
:class:`scrapy_zyte_api.Geolocation` dependency and annotating it with a
country code:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import Geolocation

    @attrs.define
    class MyPageObject(BasePage):
        product: Product
        geolocation: Annotated[Geolocation, "DE"]

.. note:: As :class:`~.Geolocation` is only useful when annotated, using it
    requires Python 3.9+.
