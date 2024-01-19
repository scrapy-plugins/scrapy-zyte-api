.. _inputs:

======
Inputs
======

:ref:`scrapy-poet integration <scrapy-poet>`, once :ref:`set up
<scrapy-poet-setup>`, allows obtaining the following :ref:`inputs
<web-poet:inputs>` from :doc:`web-poet <web-poet:index>` and
:doc:`zyte-common-items <zyte-common-items:index>` through Zyte API:

-   :class:`web_poet.BrowserHtml`

-   :class:`web_poet.BrowserResponse`

-   :class:`web_poet.AnyResponse`

    This re-uses either :class:`web_poet.BrowserResponse` *(takes priority)*
    or :class:`web_poet.HttpResponse` if they're available. If neither is
    available, it would use :class:`web_poet.HttpResponse` requested from Zyte
    API.

-   :class:`zyte_common_items.Article`

-   :class:`zyte_common_items.ArticleList`

-   :class:`zyte_common_items.ArticleNavigation`

-   :class:`zyte_common_items.JobPosting`

-   :class:`zyte_common_items.Product`

-   :class:`zyte_common_items.ProductList`

-   :class:`zyte_common_items.ProductNavigation`
