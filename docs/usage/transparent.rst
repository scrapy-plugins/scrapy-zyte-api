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


.. _transparent-sessions:

Transparent mode and sessions
=============================

:ref:`Plugin-managed sessions <session>` apply to requests that go through
Zyte API. In transparent mode, that means **all requests use session
management by default** when :setting:`ZYTE_API_SESSION_ENABLED` is ``True``,
since transparent mode routes all requests through Zyte API.

The only exception is requests with :reqmeta:`zyte_api_automap` set to
``False``, which transparent mode does not route through Zyte API, and
therefore are not subject to session management regardless of
:setting:`ZYTE_API_SESSION_ENABLED`.

If you need session management only for a subset of requests in transparent
mode, use the :reqmeta:`zyte_api_session_enabled` request metadata key to
enable or disable session management per request.
