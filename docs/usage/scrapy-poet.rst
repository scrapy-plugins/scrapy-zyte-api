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

Custom parameters
=================

scrapy-poet integration ignores both :ref:`manual <manual>` and :ref:`automatic
<automap>` Zyte API parameters.

To add Zyte API parameters to requests made by the scrapy-poet integration, use
the ``zyte_api_provider`` request meta key:

.. code-block:: python

    Request(
        "https://example.com",
        meta={
            "zyte_api_provider": {
                "requestCookies": [
                    {"name": "a", "value": "b", "domain": "example.com"},
                ],
            }
        },
    )

To add Zyte API parameters to all requests sent by the scrapy-poet integration,
use the :ref:`ZYTE_API_PROVIDER_PARAMS` setting:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_PROVIDER_PARAMS = {
        "requestCookies": [
            {"name": "a", "value": "b", "domain": "example.com"},
        ],
    }

When ``zyte_api_provider`` or :ref:`ZYTE_API_PROVIDER_PARAMS` include one of
the Zyte API extraction option parameters (e.g. ``productOptions`` for
``product``), but the final Zyte API request does not include the corresponding
extraction type, the unused options are automatically removed. So, it is safe
to use :ref:`ZYTE_API_PROVIDER_PARAMS` to set the default options for various
extraction types:

.. code-block:: python
    :caption: setting.py

    ZYTE_API_PROVIDER_PARAMS = {
        "productOptions": {"extractFrom": "httpResponseBody"},
        "productNavigationOptions": {"extractFrom": "httpResponseBody"},
    }

.. _annotations:

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

.. _geolocation:

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

.. _browser-actions:

Browser actions
---------------

You can specify browser actions by adding a :class:`scrapy_zyte_api.Actions`
dependency and annotating it with actions passed to the
:func:`scrapy_zyte_api.actions` function:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import Actions, actions


    @attrs.define
    class MyPageObject(BasePage):
        product: Product
        actions: Annotated[
            Actions,
            actions(
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
:attr:`.Actions.results` attribute of the dependency in the
resulting page object:

.. code-block:: python

    def validate_input(self):
        for action_result in self.actions.result:
            if action_result["status"] != "success":
                return Product(is_valid=False)
        return None
