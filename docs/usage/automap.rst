.. _automap:

============================
Automatic request parameters
============================

To send a Scrapy request through Zyte API letting Zyte API request parameters
be automatically chosen based on the parameters of that Scrapy request, set the
:reqmeta:`zyte_api_automap` key in :attr:`Request.meta
<scrapy.http.Request.meta>` to ``True``.

For example:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        def start_requests(self):
            yield scrapy.Request(
                url="https://quotes.toscrape.com/",
                meta={
                    "zyte_api_automap": True,
                },
            )

        def parse(self, response):
            print(response.text)
            # "<html>…</html>"

In :ref:`transparent mode <transparent>`, :reqmeta:`zyte_api_automap` is ``True``
by default.

See :ref:`request` to learn how exactly request parameters are mapped when
using automatic request parameters.


.. _request-change:

Changing parameters
===================

You may set :reqmeta:`zyte_api_automap` in :attr:`Request.meta
<scrapy.http.Request.meta>` to a :class:`dict` of Zyte API parameters to add,
modify, or remove (by setting to ``None``) automatic request parameters. This
also works in :ref:`transparent mode <transparent>`.

Enabling :http:`request:browserHtml`, :http:`request:screenshot`, or an
automatic extraction property, unsets :http:`request:httpResponseBody` and
:http:`request:httpResponseHeaders`, and makes ``Request.headers`` become
:http:`request:requestHeaders` instead of
:http:`request:customHttpRequestHeaders`. For example, the following Scrapy
request:

.. code-block:: python

    Request(
        url="https://quotes.toscrape.com",
        headers={"Referer": "https://example.com/"},
        meta={"zyte_api_automap": {"browserHtml": True}},
    )

Results in a request to the Zyte API data extraction endpoint with the
following parameters:

.. code-block:: javascript

    {
        "browserHtml": true,
        "experimental": {
            "responseCookies": true
        },
        "requestHeaders": {"referer": "https://example.com/"},
        "url": "https://quotes.toscrape.com"
    }

See also: :ref:`request-unsupported`.