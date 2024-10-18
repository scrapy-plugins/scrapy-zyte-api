.. _inputs:

======
Inputs
======

:ref:`scrapy-poet integration <scrapy-poet>`, if enabled during the
:ref:`initial setup <setup>`, allows obtaining the following :ref:`inputs
<web-poet:inputs>` from :doc:`web-poet <web-poet:index>` and
:doc:`zyte-common-items <zyte-common-items:index>` through Zyte API:

-   :class:`web_poet.BrowserHtml`

-   :class:`web_poet.BrowserResponse`

-   :class:`web_poet.AnyResponse`

    This re-uses either :class:`web_poet.BrowserResponse` *(takes priority)*
    or :class:`web_poet.HttpResponse` if they're available.

    If neither is available, it would use :class:`web_poet.HttpResponse`
    requested from Zyte API. However, if other item inputs (e.g.
    :class:`zyte_common_items.Product`) are present, it would request
    :class:`web_poet.BrowserResponse` from Zyte API unless an extraction
    source is provided.

-   :class:`zyte_common_items.Article`

-   :class:`zyte_common_items.ArticleList`

-   :class:`zyte_common_items.ArticleNavigation`

-   :class:`zyte_common_items.JobPosting`

-   :class:`zyte_common_items.JobPostingNavigation`

-   :class:`zyte_common_items.Product`

-   :class:`zyte_common_items.ProductList`

-   :class:`zyte_common_items.ProductNavigation`

Additional inputs and input annotations are also provided:

Built-in inputs
===============

.. autoclass:: scrapy_zyte_api.Actions
    :members:

.. autoclass:: scrapy_zyte_api.Geolocation
    :members:

.. autoclass:: scrapy_zyte_api.Screenshot
    :members:


Built-in input annotations
==========================

.. autoenum:: scrapy_zyte_api.ExtractFrom
    :members:

.. autofunction:: scrapy_zyte_api.actions

.. autofunction:: scrapy_zyte_api.custom_attrs
