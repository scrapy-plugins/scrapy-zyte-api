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

``ZyteApiProvider`` understands and makes use of some dependency annotations.

.. note:: Dependency annotations require Python 3.9+.

Item annotations
----------------

Item dependencies such as :class:`zyte_common_items.Product` can be annotated
directly. The only currently supported annotation is
:class:`scrapy_zyte_api.ExtractFrom`:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import ExtractFrom


    @attrs.define
    class MyPageObject(BasePage):
        product: Annotated[Product, ExtractFrom.httpResponseBody]

The provider will set the extraction options based on the annotations, so for
this code ``extractFrom`` will be set to ``httpResponseBody`` in
``productOptions``.

Geolocation
-----------

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

Actions
-------

You can specify the Zyte API actions by adding a
:class:`scrapy_zyte_api.Actions` dependency and annotating it with actions
passed to the :func:`scrapy_zyte_api.actions_list` function:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import Actions, actions_list


    @attrs.define
    class MyPageObject(BasePage):
        product: Product
        actions: Annotated[
            Actions,
            actions_list(
                [
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": "button#openDescription"},
                        "delay": 0,
                        "button": "left",
                        "onError": "return",
                    },
                    {"action": "waitForTimeout", "timeout": 5, "onError": "return"},
                ]
            ),
        ]

You can access the results of these actions in the
:attr:`.Actions.result` attribute of the dependency in the
resulting page object.
