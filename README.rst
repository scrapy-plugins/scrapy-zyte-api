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


Scrapy plugin for `Zyte API`_.

.. _Zyte API: https://docs.zyte.com/zyte-api/get-started.html


Requirements
============

* Python 3.7+
* Scrapy 2.0.1+


Installation
============

.. code-block::

    pip install scrapy-zyte-api


Configuration
=============

Replace the default ``http`` and ``https`` in Scrapy's
`DOWNLOAD_HANDLERS <https://docs.scrapy.org/en/latest/topics/settings.html#std-setting-DOWNLOAD_HANDLERS>`_
in the ``settings.py`` of your Scrapy project.

You also need to set the ``ZYTE_API_KEY``.

Lastly, make sure to `install the asyncio-based Twisted reactor
<https://docs.scrapy.org/en/latest/topics/asyncio.html#installing-the-asyncio-reactor>`_
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

The ``ZYTE_API_ENABLED`` setting, which is ``True`` by default, can be set to
``False`` to disable this plugin.


Usage
=====

You can send requests through Zyte API in one of the following ways:

-   Send all request through Zyte API by default, letting Zyte API parameters
    be chosen automatically based on your Scrapy request parameters. See
    **Using transparent mode** below.

-   Send specific requests through Zyte API, setting all Zyte API parameters
    manually, keeping full control of what is sent to Zyte API. See **Sending
    requests with manually-defined parameters** below.

-   Send specific requests through Zyte API, letting Zyte API parameters be
    chosen automatically based on your Scrapy request parameters. See **Sending
    requests with automatically-mapped parameters** below.

Zyte API response parameters are mapped into Scrapy response parameters where
possible. See **Response mapping** below for details.

If multiple requests target the same URL with different Zyte API parameters,
pass ``dont_filter=True`` to ``Request`` to prevent the duplicate request
filter of Scrapy from dropping all but the first request.


Using transparent mode
----------------------

Set the ``ZYTE_API_TRANSPARENT_MODE`` `Scrapy setting`_ to ``True`` to handle
Scrapy requests as follows:

.. _Scrapy setting: https://docs.scrapy.org/en/latest/topics/settings.html

-   By default, requests are sent through Zyte API with automatically-mapped
    parameters. See **Sending requests with automatically-mapped parameters**
    below for details about automatic request parameter mapping.

    You do not need to set the ``zyte-api-automap`` request meta key to
    ``True``, but you can set it to a dictionary to extend your Zyte API
    request parameters.

-   Requests with the ``zyte_api`` request meta key set to a ``dict`` are sent
    through Zyte API with manually-defined parameters. See **Sending requests
    with manually-defined parameters** below.

-   Requests with the ``zyte_api_automap`` request meta key set to ``False``
    are *not* sent through Zyte API.

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


Sending requests with manually-defined parameters
-------------------------------------------------

To send a Scrapy request through Zyte API with manually-defined parameters,
define your Zyte API parameters in the ``zyte_api`` key in
`Request.meta <https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
as a ``dict``.

The only exception is the ``url`` parameter, which should not be defined as a
Zyte API parameter. The value from ``Request.url`` is used automatically.

For example:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        def start_requests(self):
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
defining parameters manually and requesting ``httpResponseBody`` extraction,
remember to also request ``httpResponseHeaders`` extraction:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        def start_requests(self):
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

To learn more about Zyte API parameters, see the `data extraction usage`_ and
`API reference`_ pages of the `Zyte API documentation`_.

.. _API reference: https://docs.zyte.com/zyte-api/openapi.html
.. _data extraction usage: https://docs.zyte.com/zyte-api/usage/extract.html
.. _Zyte API documentation: https://docs.zyte.com/zyte-api/get-started.html


Sending requests with automatically-mapped parameters
-----------------------------------------------------

To send a Scrapy request through Zyte API letting Zyte API parameters be
automatically chosen based on the parameters of that Scrapy request, set the
``zyte_api_automap`` key in
`Request.meta <https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
to ``True``.

For example:

.. code-block:: python

    import scrapy


    class SampleQuotesSpider(scrapy.Spider):
        name = "sample_quotes"

        def start_requests(self):
            yield scrapy.Request(
                url="https://quotes.toscrape.com/",
                meta={
                    "zyte_api": {
                        "zyte_api_automap": True,
                    }
                },
            )

        def parse(self, response):
            print(response.text)
            # "<html>…</html>"

See also **Using transparent mode** above and **Automated request parameter
mapping** below.


Response mapping
----------------

Zyte API responses are mapped with one of the following classes:

-   ``scrapy_zyte_api.responses.ZyteAPITextResponse``, a subclass of
    ``scrapy.http.TextResponse``, is used to map text responses, i.e. responses
    with ``browserHtml`` or responses with both ``httpResponseBody`` and
    ``httpResponseHeaders`` with a text body (e.g. plain text, HTML, JSON).

-   ``scrapy_zyte_api.responses.ZyteAPIResponse``, a subclass of
    ``scrapy.http.Response``, is used to map any other response.

Zyte API response parameters are mapped into response class attributes where
possible:

-   ``url`` becomes ``response.url``.

-   ``statusCode`` becomes ``response.status``.

-   ``httpResponseHeaders`` becomes ``response.headers``.

-   ``browserHtml`` and ``httpResponseBody`` are mapped into both
    ``response.text`` (``str``) and ``response.body`` (``bytes``).

    If none of these parameters were present, e.g. if the only requested output
    was ``screenshot``, ``response.text`` and ``response.body`` would be empty.

    If a future version of Zyte API supported requesting both outputs on the
    same request, and both parameters were present, ``browserHtml`` would be
    the one mapped into ``response.text`` and ``response.body``.

Both response classes have a ``raw_zyte_api`` attribute that contains a
``dict`` with the complete, raw response from Zyte API, where you can find all
Zyte API response parameters, including those that are not mapped into other
response class atttributes.

For example, for a request for ``httpResponseBody`` and
``httpResponseHeaders``, you would get:

.. code-block:: python

    def parse(self, response):
        print(response.url)
        # "https://quotes.toscrape.com/"
        print(response.status)
        # 200
        print(response.headers)
        # {b"Content-Type": [b"text/html"], …}
        print(response.text)
        # "<html>…</html>"
        print(response.body)
        # b"<html>…</html>"
        print(response.raw_api_response)
        # {
        #     "url": "https://quotes.toscrape.com/",
        #     "statusCode": 200,
        #     "httpResponseBody": "PGh0bWw+4oCmPC9odG1sPg==",
        #     "httpResponseHeaders": […],
        # }

For a request for ``screenshot``, on the other hand, the response would look
as follows:

.. code-block:: python

    def parse(self, response):
        print(response.url)
        # "https://quotes.toscrape.com/"
        print(response.status)
        # 200
        print(response.headers)
        # {}
        print(response.text)
        # ""
        print(response.body)
        # b""
        print(response.raw_api_response)
        # {
        #     "url": "https://quotes.toscrape.com/",
        #     "statusCode": 200,
        #     "screenshot": "iVBORw0KGgoAAAANSUh…",
        # }
        from base64 import b64decode
        print(b64decode(response.raw_api_response["screenshot"]))
        # b'\x89PNG\r\n\x1a\n\x00\x00\x00\r…'


Automated request parameter mapping
-----------------------------------

When you enable automated request parameter mapping, be it through transparent
mode (see **Using transparent mode** above) or for a specific request (see
**Sending requests with automatically-mapped parameters** above), Zyte API
parameters are chosen as follows by default:

-   ``httpResponseBody`` and ``httpResponseHeaders`` are set to ``True``.

    This is subject to change without prior notice in future versions of
    scrapy-zyte-api, so please account for the following:

    -   If you are requesting a binary resource, such as a PDF file or an
        image file, set ``httpResponseBody`` to ``True`` explicitly in your
        requests:

        .. code-block:: python

            Request(
                url="https://toscrape.com/img/zyte.png",
                meta={
                    "zyte_api": {
                        "zyte_api_automap": {"httpResponseBody": True},
                    }
                },
            )

        In the future, we may stop setting ``httpResponseBody`` to ``True`` by
        default, and instead use a different, new Zyte API parameter that only
        works for non-binary responses (e.g. HMTL, JSON, plain text).

    -   If you need to access response headers, be it through
        ``response.headers`` or through
        ``response.raw_zyte_api["httpResponseHeaders"]``, set
        ``httpResponseHeaders`` to ``True`` explicitly in your requests:

        .. code-block:: python

            Request(
                url="https://toscrape.com/",
                meta={
                    "zyte_api": {
                        "zyte_api_automap": {"httpResponseHeaders": True},
                    }
                },
            )

        At the moment we request response headers because some response headers
        are necessary to properly decode the response body as text. In the
        future, Zyte API may be able to handle this decoding automatically, so
        we would stop setting ``httpResponseHeaders`` to ``True`` by default.

-   ``Request.url`` becomes ``url``, same as in requests with manually-defined
    parameters.

-   If ``Request.method`` is something other than ``"GET"``, it becomes
    ``httpRequestMethod``.

-   ``Request.headers`` become ``customHttpRequestHeaders``.

-   ``Request.body`` becomes ``httpRequestBody``.

For example, the following Scrapy request:

.. code-block:: python

    Request(
        method="POST"
        url="https://httpbin.org/anything",
        headers={"Content-Type": "application/json"},
        body=b'{"foo": "bar"}',
    )

Results in a request to the Zyte API data extraction endpoint with the
following parameters:

.. code-block:: javascript

    {
        "httpResponseBody": true,
        "httpResponseHeaders": true,
        "url": "https://httpbin.org/anything",
        "httpRequestMethod": "POST",
        "customHttpRequestHeaders": [{"name": "Content-Type", "value": "application/json"}],
        "httpRequestBody": "eyJmb28iOiAiYmFyIn0="
    }

You may set the ``zyte_api_automap`` key in
`Request.meta <https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
to a ``dict`` of Zyte API parameters to extend or override choices made by
automated request parameter mapping.

Setting ``browserHtml`` or ``screenshot`` to ``True`` unsets
``httpResponseBody`` and ``httpResponseHeaders``, and makes ``Request.headers``
become ``requestHeaders`` instead of ``customHttpRequestHeaders``. For example,
the following Scrapy request:

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
        "url": "https://quotes.toscrape.com",
        "requestHeaders": {"referer": "https://example.com/"},
    }

When mapping headers, headers not supported by Zyte API are excluded from the
mapping by default. Use the following `Scrapy settings`_ to change which
headers are included or excluded from header mapping:

.. _Scrapy settings: https://docs.scrapy.org/en/latest/topics/settings.html

-   ``ZYTE_API_SKIP_HEADERS`` determines headers that must *not* be mapped as
    ``customHttpRequestHeaders``, and its default value is:

    .. code-block:: python

       ["Cookie", "User-Agent"]

-   ``ZYTE_API_BROWSER_HEADERS`` determines headers that *can* be mapped as
    ``requestHeaders``. It is a ``dict``, where keys are header names and
    values are the key that represents them in ``requestHeaders``. Its default
    value is:

    .. code-block:: python

       {"Referer": "referer"}

To maximize support for potential future changes in Zyte API, automated
request parameter mapping allows some parameter values and parameter
combinations that Zyte API does not currently support, and may never support:

-   ``Request.method`` becomes ``httpRequestMethod`` even for unsupported_
    ``httpRequestMethod`` values, and even if ``httpResponseBody`` is unset.

    .. _unsupported: https://docs.zyte.com/zyte-api/usage/extract.html#zyte-api-set-method

-   You can set ``customHttpRequestHeaders`` or ``requestHeaders`` to ``True``
    to force their mapping from ``Request.headers`` in scenarios where they
    would not be mapped otherwise.

    Conversely, you can set ``customHttpRequestHeaders`` or ``requestHeaders``
    to ``False`` to prevent their mapping from ``Request.headers``.

-   ``Request.body`` becomes ``httpRequestBody`` even if ``httpResponseBody``
    is unset.

-   You can set ``httpResponseBody`` to ``False`` (which unsets the parameter),
    and not set ``browserHtml`` or ``screenshot`` to ``True``. In this case,
    ``Request.headers`` is mapped as ``requestHeaders``.

-   You can set ``httpResponseBody`` to ``True`` and also set ``browserHtml``
    or ``screenshot`` to ``True``. In this case, ``Request.headers`` is mapped
    both as ``customHttpRequestHeaders`` and as ``requestHeaders``, and
    ``browserHtml`` is used as the Scrapy response body.


Setting default parameters
==========================

Often the same configuration needs to be used for all Zyte API requests. For
example, all requests may need to set the same geolocation, or the spider only
uses ``browserHtml`` requests.

The following settings allow you to define Zyte API parameters to be included
in all requests:

-   ``ZYTE_API_DEFAULT_PARAMS`` is a ``dict`` of parameters to be combined with
    manually-defined parameters. See **Sending requests with manually-defined
    parameters** above.

    You may set the ``zyte_api`` request meta key to an empty ``dict`` to only
    use default parameters for that request.

-   ``ZYTE_API_AUTOMAP_PARAMS`` is a ``dict`` of parameters to be combined with
    automatically-mapped parameters. See **Sending requests with
    automatically-mapped parameters** above.

For example, if you set ``ZYTE_API_DEFAULT_PARAMS`` to
``{"geolocation": "US"}`` and ``zyte_api`` to ``{"browserHtml": True}``,
``{"url: "…", "geolocation": "US", "browserHtml": True}`` is sent to Zyte API.

Parameters in these settings are merged with request-specific parameters, with
request-specific parameters taking precedence.

``ZYTE_API_DEFAULT_PARAMS`` has no effect on requests that use automated
request parameter mapping, and ``ZYTE_API_AUTOMAP_PARAMS`` has no effect on
requests that use manually-defined parameters.

When using transparent mode (see **Using transparent mode** above), be careful
of which parameters you define through ``ZYTE_API_AUTOMAP_PARAMS``. In
transparent mode, all Scrapy requests go through Zyte API, even requests that
Scrapy sends automatically, such as those for ``robots.txt`` files when
ROBOTSTXT_OBEY_ is ``True``, or those for sitemaps when using a `sitemap
spider`_. Certain parameters, like ``browserHtml`` or ``screenshot``, are not
meant to be used for every single request.

.. _ROBOTSTXT_OBEY: https://docs.scrapy.org/en/latest/topics/settings.html#robotstxt-obey
.. _sitemap spider: https://docs.scrapy.org/en/latest/topics/spiders.html#sitemapspider


Customizing the retry policy
============================

API requests are retried automatically using the default retry policy of
`python-zyte-api`_.

API requests that exceed retries are dropped. You cannot manage API request
retries through Scrapy downloader middlewares.

Use the ``ZYTE_API_RETRY_POLICY`` setting or the ``zyte_api_retry_policy``
request meta key to override the default `python-zyte-api`_ retry policy with a
custom retry policy.

A custom retry policy must be an instance of `tenacity.AsyncRetrying`_.

Scrapy settings must be picklable, which `retry policies are not
<https://github.com/jd/tenacity/issues/147>`_, so you cannot assign retry
policy objects directly to the ``ZYTE_API_RETRY_POLICY`` setting, and must use
their import path string instead.

When setting a retry policy through request meta, you can assign the
``zyte_api_retry_policy`` request meta key either the retry policy object
itself or its import path string. If you need your requests to be serializable,
however, you may also need to use the import path string.

For example, to also retry HTTP 521 errors the same as HTTP 520 errors, you can
subclass RetryFactory_ as follows:

.. code-block:: python

    # project/retry_policies.py
    from tenacity import retry_if_exception, RetryCallState
    from zyte_api.aio.errors import RequestError
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

    CUSTOM_RETRY_POLICY = CustomRetryFactory().build()

    # project/settings.py
    ZYTE_API_RETRY_POLICY = "project.retry_policies.CUSTOM_RETRY_POLICY"

.. _python-zyte-api: https://github.com/zytedata/python-zyte-api
.. _RetryFactory: https://github.com/zytedata/python-zyte-api/blob/main/zyte_api/aio/retry.py
.. _tenacity.AsyncRetrying: https://tenacity.readthedocs.io/en/latest/api.html#tenacity.AsyncRetrying


Stats
=====

Stats from python-zyte-api_ are exposed as Scrapy stats with the
``scrapy-zyte-api`` prefix.
