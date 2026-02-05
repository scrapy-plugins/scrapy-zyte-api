.. _manual:

=========================
Manual request parameters
=========================

To send a Scrapy request through Zyte API with manually-defined Zyte API
request parameters, define your parameters in the :reqmeta:`zyte_api` key in
:attr:`Request.meta <scrapy.http.Request.meta>` as a :class:`dict`.

The only exception is the :http:`request:url` parameter, which should not be
defined as a Zyte API parameter. The value from :attr:`Request.url
<scrapy.http.Request.url>` is used automatically.

For example:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        async def start(self):
            yield scrapy.Request(
                url="https://quotes.toscrape.com/",
                meta={
                    "zyte_api": {
                        "browserHtml": True,
                    }
                },
            )

        def parse(self, response):
            print(response.text)
            # "<html>…</html>"

Note that response headers are necessary for raw response decoding. When
defining parameters manually and requesting :http:`request:httpResponseBody`,
remember to also request :http:`request:httpResponseHeaders`:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        async def start(self):
            yield scrapy.Request(
                url="https://quotes.toscrape.com/",
                meta={
                    "zyte_api": {
                        "httpResponseBody": True,
                        "httpResponseHeaders": True,
                    }
                },
            )

        def parse(self, response):
            print(response.text)
            # "<html>…</html>"

To learn more about Zyte API parameters, see the upstream :ref:`usage
<zapi-usage>` and :ref:`API reference <zapi-reference>` pages.
