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

You can send a request through Zyte API in one of the following ways:

-   Setting all Zyte API parameters manually, keeping full control of what is
    sent to Zyte API. See **Sending requests with manually-defined parameters**
    below.

-   Letting Zyte API parameters be chosen automatically based on your Scrapy
    request parameters where possible. See **Sending requests with
    automatically-mapped parameters** below.

The raw Zyte API response can be accessed via the ``raw_api_response``
attribute of the response object.

When you use the Zyte API parameters ``browserHtml``, ``httpResponseBody``, or
``httpResponseHeaders``, the response body and headers are set accordingly.

Note that, for Zyte API requests, the spider gets responses of
``ZyteAPIResponse`` and ``ZyteAPITextResponse`` types, which are respectively
subclasses of ``scrapy.http.Response`` and ``scrapy.http.TextResponse``.

If multiple requests target the same URL with different Zyte API parameters,
pass ``dont_filter=True`` to ``Request``.


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
                url="http://quotes.toscrape.com/",
                meta={
                    "zyte_api": {
                        "browserHtml": True,
                    }
                },
            )

        def parse(self, response):
            print(response.raw_api_response)
            # {
            #     'url': 'https://quotes.toscrape.com/',
            #     'statusCode': 200,
            #     'browserHtml': '<html>…</html>',
            # }

See the `Zyte API documentation`_ to learn about Zyte API parameters.

.. _Zyte API documentation: https://docs.zyte.com/zyte-api/get-started.html


Sending requests with automatically-mapped parameters
-----------------------------------------------------

To send a Scrapy request through Zyte API letting Zyte API parameters be
automatically chosen based on the parameters of that Scrapy request, set the
``zyte_api_automap`` key in
`Request.meta <https://docs.scrapy.org/en/latest/topics/request-response.html#scrapy.http.Request.meta>`_
to ``True``. See also **Using transparent mode** below.

Automated parameter mapping chooses Zyte API parameters as follows by default:

-   ``httpResponseBody`` and ``httpResponseHeaders`` are set to ``True``.

-   ``Request.url`` becomes ``url``, same as in requests with manually-defined
    parameters.

-   If ``Request.method`` is something other than ``"GET"``, it becomes
    ``httpRequestMethod``.

-   ``Request.headers`` become ``customHttpRequestHeaders``.

-   ``Request.body`` is base64-encoded as ``httpRequestBody``.

Instead of setting ``zyte_api_automap`` to ``True``, you may set it to a
``dict`` of Zyte API parameters to extend or override choices made by automated
parameter mapping. Some parameters modify the result of automated parameter
mapping as a side effect:

-   Setting ``browserHtml`` or ``screenshot`` to ``True`` unsets
    ``httpResponseBody``, and makes ``Request.headers`` become
    ``requestHeaders`` instead of ``customHttpRequestHeaders``.

-   Setting ``screenshot`` to ``True`` without also setting ``browserHtml`` to
    ``True`` unsets ``httpResponseHeaders``.

When mapping headers, unsupported headers are excluded from the mapping. Use
the following settings to change which headers are mapped and how they are
mapped:

-   ``ZYTE_API_UNSUPPORTED_HEADERS`` determines headers that *cannot* be mapped
    as ``customHttpRequestHeaders``, and its default value is:

    .. code-block:: python

       ["Cookie", "User-Agent"]

-   ``ZYTE_API_BROWSER_HEADERS`` determines headers that *can* be mapped as
    ``requestHeaders``. It is a ``dict``, where keys are header names and
    values are the key that represents them in ``requestHeaders``. Its default
    value is:

    .. code-block:: python

       {"Referer": "referer"}

To maximize support for potential future changes in Zyte API, automated
parameter mapping allows some parameter values and parameter combinations that
Zyte API does not currently support, and may never support:

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


Using transparent mode
----------------------

Set the ``ZYTE_API_TRANSPARENT_MODE`` setting to ``True`` to handle Scrapy
requests as follows:

-   Requests with the ``zyte_api_automap`` request meta key set to ``False``
    are *not* sent through Zyte API.

-   Requests with the ``zyte_api`` request meta key set to a ``dict`` are sent
    through Zyte API with manually-defined parameters. See **Sending requests
    with manually-defined parameters** above.

-   All other requests are sent through Zyte API with automatically-mapped
    parameters. See **Sending requests with automatically-mapped parameters**
    above.

    You do not need to set the ``zyte-api-automap`` request meta key to
    ``True``, but you can set it to a dictionary to extend your request
    parameters.


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
