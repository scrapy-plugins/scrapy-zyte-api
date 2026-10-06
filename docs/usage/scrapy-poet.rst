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

.. _annotations:

Dependency annotations
======================

``ZyteApiProvider`` understands and makes use of some dependency annotations.

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

.. _network-capture:

Network capture
---------------

You can capture network responses made during browser rendering by adding a
:class:`scrapy_zyte_api.NetworkCapture` dependency and annotating it with
filters passed to the :func:`scrapy_zyte_api.network_capture` function:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import NetworkCapture, network_capture


    @attrs.define
    class MyPageObject(BasePage):
        response: BrowserResponse
        network: Annotated[
            NetworkCapture,
            network_capture(
                [
                    {
                        "filterType": "url",
                        "value": "/api/",
                        "matchType": "contains",
                        "httpResponseBody": True,
                    },
                    {"filterType": "resourceType", "value": "xhr"},
                ]
            ),
        ]

Each filter is a :class:`~scrapy_zyte_api.NetworkCaptureFilter` dict. A
response is captured if it matches any filter. Set ``httpResponseBody`` to
``True`` on a filter to include the decoded response body for responses matched
by that filter.

You can access the captured responses as
:class:`~scrapy_zyte_api.CapturedResponse` objects in the
:attr:`.NetworkCapture.results` attribute:

.. code-block:: python

    def parse_network_capture(self):
        for captured in self.network.results:
            if "/api/products" in captured.url:
                data = json.loads(captured.body)
                ...

.. _custom-attrs:

Custom attribute extraction
---------------------------

You can request custom attribute extraction by using either a
:class:`zyte_common_items.CustomAttributes` dependency (if you need both the
attribute values and the attribute extraction metadata) or a
:class:`zyte_common_items.CustomAttributesValues` dependency (if you only need
the values). You need to annotate it with input data as a dictionary and, if
needed, a dictionary with extraction options. You should use the
:func:`scrapy_zyte_api.custom_attrs` function to create the annotation:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import custom_attrs
    from zyte_common_items import CustomAttributes


    @attrs.define
    class MyPageObject(BasePage):
        product: Product
        custom_attributes: Annotated[
            CustomAttributes,
            custom_attrs(
                {"name": {"type": "string", "description": "name of the product"}},
                {"method": "generate"},
            ),
        ]

You can then access the results as the dependency value:

.. code-block:: python

        def parse_page(self, response: DummyResponse, page: MyPageObject):
            ...
            for k, v in page.custom_attributes.values.items():
                ...


.. _zyte-api-params:

Arbitrary parameters
--------------------

For Zyte API parameters without a dedicated input or annotation, you can add a
:class:`scrapy_zyte_api.ZyteApiParams` dependency, annotated with a dictionary
of Zyte API parameters passed to the :func:`scrapy_zyte_api.zyte_api_params`
function:

.. code-block:: python

    from typing import Annotated

    from scrapy_zyte_api import ZyteApiParams, zyte_api_params


    @attrs.define
    class MyPageObject(BasePage):
        product: Product
        params: Annotated[ZyteApiParams, zyte_api_params({"ipType": "residential"})]

Those parameters are included into the Zyte API request that the scrapy-poet
integration sends to get the other inputs of the page object.

You can access the resulting Zyte API request parameters, including those set
by other means, as the dependency value:

.. code-block:: python

        def parse_page(self, response: DummyResponse, page: MyPageObject):
            ...
            print(page.params.params)

Mind the following:

-   Prefer :ref:`inputs <inputs>` and the annotations above when they cover
    what you need. Setting a parameter that has a dedicated input or annotation
    (e.g. ``geolocation`` or ``actions``) through
    :class:`~scrapy_zyte_api.ZyteApiParams` logs a warning.

-   Parameters set this way take precedence over the
    :setting:`ZYTE_API_PROVIDER_PARAMS` setting, but not over the
    :reqmeta:`zyte_api_provider` request metadata key, which always wins and
    hence remains a per-request override.

-   If 2 :class:`~scrapy_zyte_api.ZyteApiParams` dependencies of the same
    request set the same parameter to different values, a :exc:`ValueError`
    exception is raised. Setting the ``url`` parameter also raises
    :exc:`ValueError`.

-   As with :reqmeta:`zyte_api_provider`, parameters that :ref:`do not change
    the request fingerprint <fingerprint-params>` do not change it here either,
    so 2 requests that only differ on such a parameter are considered
    duplicates.

-   Annotations are static, so you cannot build these parameters at run time,
    e.g. based on :class:`~web_poet.page_inputs.page_params.PageParams`. Use
    :reqmeta:`zyte_api_provider` or :ref:`additional requests
    <web-poet:additional-requests>` for that.


Custom parameters
=================

scrapy-poet integration ignores both :ref:`manual <manual>` and :ref:`automatic
<automap>` Zyte API parameters.

Whenever you can, use :ref:`inputs <inputs>` and :ref:`dependency annotations
<annotations>` to get additional Zyte API parameters into Zyte API requests
made by the scrapy-poet integration, including
:class:`~scrapy_zyte_api.ZyteApiParams` for :ref:`arbitrary parameters
<zyte-api-params>`.

If that is not possible, e.g. if parameters must be built at run time or must
be defined in the spider, you can add Zyte API parameters to requests made by
the scrapy-poet integration with the :reqmeta:`zyte_api_provider` request
metadata key or the :setting:`ZYTE_API_PROVIDER_PARAMS` setting.

When :reqmeta:`zyte_api_provider` or :setting:`ZYTE_API_PROVIDER_PARAMS`
include one of the Zyte API extraction option parameters (e.g.
``productOptions`` for ``product``), but the final Zyte API request does not
include the corresponding extraction type, the unused options are automatically
removed. So, it is safe to use :setting:`ZYTE_API_PROVIDER_PARAMS` to set the
default options for various extraction types:

.. code-block:: python
    :caption: setting.py

    ZYTE_API_PROVIDER_PARAMS = {
        "productOptions": {"extractFrom": "httpResponseBody"},
        "productNavigationOptions": {"extractFrom": "httpResponseBody"},
    }

When both :reqmeta:`zyte_api_provider` and :setting:`ZYTE_API_PROVIDER_PARAMS`
are defined, they are combined, with :reqmeta:`zyte_api_provider` taking
precedence in case of conflict. :ref:`Parameters from page objects
<zyte-api-params>` fall in between: they override
:setting:`ZYTE_API_PROVIDER_PARAMS`, and are overridden by
:reqmeta:`zyte_api_provider`.
