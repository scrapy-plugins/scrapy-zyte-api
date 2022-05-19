===============
scrapy-zyte-api
===============

.. image:: https://img.shields.io/pypi/v/scrapy-zyte-api.svg
   :target: https://pypi.python.org/pypi/scrapy-zyte-api
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/scrapy-zyte-api.svg
   :target: https://pypi.python.org/pypi/scrapy-zyte-api
   :alt: Supported Python Versions

.. image:: https://github.com/scrapy-plugins/scrapy-zyte-api/actions/workflows/test.yml/badge.svg
   :target: https://github.com/scrapy-plugins/scrapy-zyte-api/actions/workflows/test.yml
   :alt: Automated tests

.. image:: https://codecov.io/gh/scrapy-plugins/scrapy-zyte-api/branch/main/graph/badge.svg?token=iNYIk4nfyd
   :target: https://codecov.io/gh/scrapy-plugins/scrapy-zyte-api
   :alt: Coverage report

Requirements
------------

* Python 3.7+
* Scrapy

Installation
------------

.. code-block::

    pip install scrapy-zyte-api

This package requires Python 3.7+.

Configuration
-------------

Replace the default ``http`` and ``https`` in Scrapy's
`DOWNLOAD_HANDLERS <https://docs.scrapy.org/en/latest/topics/settings.html#std-setting-DOWNLOAD_HANDLERS>`_
in the ``settings.py`` of your Scrapy project.

You also need to set the ``ZYTE_API_KEY``.

Lastly, make sure to `install the asyncio-based Twisted reactor
<https://docs.scrapy.org/en/latest/topics/asyncio.html#installing-the-asyncio-reactor)>`_
in the ``settings.py`` file as well:

Here's example of the things needed inside a Scrapy project's ``settings.py`` file:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "http": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler",
        "https": "scrapy_zyte_api.handler.ScrapyZyteAPIDownloadHandler"
    }

    # Having the following in the env var would also work.
    ZYTE_API_KEY = "<your API key>"

    TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

Usage
-----

Set the ``zyte_api`` `Request.meta
<https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
key to download a request using Zyte API. Full list of parameters is provided in the
`Zyte API Specification <https://docs.zyte.com/zyte-api/openapi.html#zyte-openapi-spec>`_.

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        def start_requests(self):

            yield scrapy.Request(
                url="http://books.toscrape.com/",
                callback=self.parse,
                meta={
                    "zyte_api": {
                        "browserHtml": True,
                        "geolocation": "US",  # You can set any Geolocation region you want.
                        "javascript": True,
                        "echoData": {"some_value_I_could_track": 123},
                    }
                },
            )

        def parse(self, response):
            yield {"URL": response.url, "status": response.status, "HTML": response.body}

            print(response.zyte_api)
            # {
            #     'url': 'https://quotes.toscrape.com/',
            #     'browserHtml': '<html> ... </html>',
            #     'echoData': {'some_value_I_could_track': 123},
            # }

            print(response.request.meta)
            # {
            #     'zyte_api': {
            #         'browserHtml': True,
            #         'geolocation': 'US',
            #         'javascript': True,
            #         'echoData': {'some_value_I_could_track': 123}
            #     },
            #     'download_timeout': 180.0,
            #     'download_slot': 'quotes.toscrape.com'
            # }

The raw Zyte API Response can be accessed via the ``zyte_api`` attribute
of the response object. Note that such responses are of ``ZyteAPIResponse`` and
``ZyteAPITextResponse`` which are respectively subclasses of ``scrapy.http.Response``
and ``scrapy.http.TextResponse``. Such classes are needed to hold the raw Zyte API
responses.
