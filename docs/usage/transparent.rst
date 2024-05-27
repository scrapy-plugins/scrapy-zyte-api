.. _transparent:

================
Transparent mode
================

Set :setting:`ZYTE_API_TRANSPARENT_MODE` to ``True`` to handle requests as
follows:

-   By default, requests are sent with :ref:`automatic request
    parameters <automap>`.

-   Requests with :reqmeta:`zyte_api` set to a ``dict`` are sent with
    :ref:`manual request parameters <manual>`.

-   Requests with :reqmeta:`zyte_api_automap` set to ``False`` are *not* sent
    through Zyte API.

For example:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"
        start_urls = ["https://quotes.toscrape.com/"]

        custom_settings = {
            "ZYTE_API_TRANSPARENT_MODE": True,
        }

        def parse(self, response):
            print(response.text)
            # "<html>…</html>"
