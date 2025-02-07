.. _fingerprint:

Request fingerprinting
======================

The request fingerprinter class of scrapy-zyte-api ensures that Scrapy 2.7 and
later generate unique :ref:`request fingerprints <request-fingerprints>` for
Zyte API requests :ref:`based on some of their parameters
<fingerprint-params>`.

For example, a request for :http:`request:browserHtml` and a request for
:http:`request:screenshot` with the same target URL are considered different
requests. Similarly, requests with the same target URL but different
:http:`request:actions` are also considered different requests.

Use :setting:`ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS` to define a custom
request fingerprinting for requests that do not go through Zyte API.


Request fingerprinting below Scrapy 2.7
---------------------------------------

If you have a Scrapy version lower than Scrapy 2.7, Zyte API parameters are not
taken into account for request fingerprinting. This can cause some Scrapy
components, like the filter of duplicate requests or the HTTP cache extension,
to interpret 2 different requests as being the same.

To avoid most issues, use :ref:`automatic request parameters <automap>`, either
through :ref:`transparent mode <transparent>` or setting
:reqmeta:`zyte_api_automap` to ``True`` in :attr:`Request.meta
<scrapy.http.Request.meta>`, and then use :class:`~scrapy.http.Request`
attributes instead of :attr:`Request.meta <scrapy.http.Request.meta>` as much
as possible. Unlike :attr:`Request.meta <scrapy.http.Request.meta>`,
:class:`~scrapy.http.Request` attributes do affect request fingerprints in
Scrapy versions older than Scrapy 2.7.

For requests that must have the same :class:`~scrapy.http.Request` attributes
but should still be considered different, such as browser-based requests with
different URL fragments, you can set ``dont_filter=True`` when creating your
request to prevent the duplicate filter of Scrapy to filter any of them out.
For example:

.. code-block:: python

    yield Request(
        "https://toscrape.com#1",
        meta={"zyte_api_automap": {"browserHtml": True}},
        dont_filter=True,
    )
    yield Request(
        "https://toscrape.com#2",
        meta={"zyte_api_automap": {"browserHtml": True}},
        dont_filter=True,
    )

Note, however, that for other Scrapy components, like the HTTP cache
extensions, these 2 requests would still be considered identical.
