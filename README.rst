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
* Scrapy 2.6+

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
in the ``settings.py`` file as well.

Here's an example of the things needed inside a Scrapy project's ``settings.py`` file:

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

To enable a ``scrapy.Request`` to go through Zyte Data API, the ``zyte_api`` key in
`Request.meta <https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
must be present and contain a dict with Zyte API parameters:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        def start_requests(self):
            yield scrapy.Request(
                url="http://quotes.toscrape.com/",
                callback=self.parse,
                meta={
                    "zyte_api": {
                        "browserHtml": True,
                    }
                },
            )

        def parse(self, response):
            yield {"URL": response.url, "HTML": response.body}

            print(response.raw_api_response)
            # {
            #     'url': 'https://quotes.toscrape.com/',
            #     'browserHtml': '<html> ... </html>',
            # }

You can see the full list of parameters in the `Zyte Data API Specification
<https://docs.zyte.com/zyte-api/openapi.html#zyte-openapi-spec>`_.
The ``url`` parameter is filled automatically from ``request.url``, other 
parameters should be set explicitly.

The raw Zyte Data API response can be accessed via the ``raw_api_response``
attribute of the response object.

When you use the Zyte Data API parameters ``browserHtml``, 
``httpResponseBody``, or ``httpResponseHeaders``, the response body and headers 
are set accordingly.

Note that, for Zyte Data API requests, the spider gets responses of
``ZyteAPIResponse`` and ``ZyteAPITextResponse`` types,
which are respectively subclasses of ``scrapy.http.Response``
and ``scrapy.http.TextResponse``.

If multiple requests target the same URL with different Zyte Data API
parameters, pass ``dont_filter=True`` to ``Request``.

Setting default parameters
--------------------------
Often the same configuration needs to be used for all Zyte API requests.
For example, all requests may need to set the same geolocation, or
the spider only uses ``browserHtml`` requests.

To set the default parameters for Zyte API enabled requests, you can set the
following in the ``settings.py`` file or `any other settings within Scrapy
<https://docs.scrapy.org/en/latest/topics/settings.html#populating-the-settings>`_:

.. code-block:: python

    ZYTE_API_DEFAULT_PARAMS = {
        "browserHtml": True,
        "geolocation": "US",
    }


``ZYTE_API_DEFAULT_PARAMS`` works if the ``zyte_api``
key in `Request.meta <https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
is set, i.e. having ``ZYTE_API_DEFAULT_PARAMS`` doesn't make all requests
to go through Zyte Data API. Parameters in ``ZYTE_API_DEFAULT_PARAMS`` are 
merged with parameters set via the ``zyte_api`` meta key, with the values in 
meta taking priority.

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        custom_settings = {
            "ZYTE_API_DEFAULT_PARAMS": {
                "geolocation": "US",  # You can set any Geolocation region you want.
            }
        }

        def start_requests(self):
            yield scrapy.Request(
                url="http://quotes.toscrape.com/",
                callback=self.parse,
                meta={
                    "zyte_api": {
                        "browserHtml": True,
                        "javascript": True,
                        "echoData": {"some_value_I_could_track": 123},
                    }
                },
            )

        def parse(self, response):
            yield {"URL": response.url, "HTML": response.body}

            print(response.raw_api_response)
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

There is a shortcut, in case a request uses the same parameters as
defined in the ``ZYTE_API_DEFAULT_PARAMS`` setting, without any further
customization - the ``zyte_api`` meta key can be set to ``True`` or ``{}``:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        custom_settings = {
            "ZYTE_API_DEFAULT_PARAMS": {
                "browserHtml": True,
            }
        }

        def start_requests(self):
            yield scrapy.Request(
                url="http://quotes.toscrape.com/",
                callback=self.parse,
                meta={"zyte_api": True},
            )

        def parse(self, response):
            yield {"URL": response.url, "HTML": response.body}

            print(response.raw_api_response)
            # {
            #     'url': 'https://quotes.toscrape.com/',
            #     'browserHtml': '<html> ... </html>',
            # }

            print(response.request.meta)
            # {
            #     'zyte_api': {
            #         'browserHtml': True,
            #     },
            #     'download_timeout': 180.0,
            #     'download_slot': 'quotes.toscrape.com'
            # }

Customizing the retry policy
----------------------------

API requests are retried automatically using the default retry policy of
`python-zyte-api`_.

API requests that exceed retries are dropped. You cannot manage API request
retries through Scrapy downloader middlewares.

Use the ``ZYTE_API_RETRY_POLICY`` setting or the ``zyte_api_retry_policy``
request meta key to override the default `python-zyte-api`_ retry policy with a
custom retry policy.

A custom retry policy must be an instance of `tenacity.AsyncRetrying`_.

For example, to also retry HTTP 521 errors the same as HTTP 520 errors, you can
subclass RetryFactory_ as follows::

    # settings.py
    from tenacity import retry_if_exception
    from zyte_api.aio.retry import RetryFactory

    def is_http_521(exc: BaseException) -> bool:
        return isinstance(exc, RequestError) and exc.status == 521

    class CustomRetryFactory(RetryFactory):

        retry_condition = (
            RetryFactory.retry_condition
            | retry_if_exception(is_http_521)
        )

        def wait(self, retry_state: RetryCallState) -> float:
            if is_http_521(retry_state.outcome.exception()):
                return self.temporary_download_error_wait(retry_state=retry_state)
            return super().wait(retry_state)

        def stop(self, retry_state: RetryCallState) -> bool:
            if is_http_521(retry_state.outcome.exception()):
                return self.temporary_download_error_stop(retry_state)
            return super().stop(retry_state)

    ZYTE_API_RETRY_POLICY = CustomRetryFactory().build()

.. _python-zyte-api: https://github.com/zytedata/python-zyte-api
.. _RetryFactory: https://github.com/zytedata/python-zyte-api/blob/main/zyte_api/aio/retry.py
.. _tenacity.AsyncRetrying: https://tenacity.readthedocs.io/en/latest/api.html#tenacity.AsyncRetrying


Stats
-----

Stats from python-zyte-api_ are exposed as Scrapy stats with the
``scrapy-zyte-api`` prefix.
