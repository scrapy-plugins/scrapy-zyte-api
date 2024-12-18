.. _retry:

=======
Retries
=======

To make :ref:`error handling <zapi-errors>` easier, scrapy-zyte-api lets
you :ref:`handle successful Zyte API responses as usual <retry-successful>`,
but :ref:`implements a more advanced retry mechanism for rate-limiting and
unsuccessful responses <retry-non-successful>`.

.. _retry-successful:

Retrying successful Zyte API responses
======================================

When a :ref:`successful Zyte API response <zapi-successful-responses>` is
received, a Scrapy response object is built based on the upstream website
response (see :ref:`response`), and passed to your :ref:`downloader middlewares
<topics-downloader-middleware>` and :ref:`spider callback <topics-spiders>`.

Usually, these responses do not need to be retried. If they do, you can retry
them using Scrapy’s built-in retry middleware
(:class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware`) or its
:func:`~scrapy.downloadermiddlewares.retry.get_retry_request` function.


.. _retry-non-successful:

Retrying non-successful Zyte API responses
==========================================

When a :ref:`rate-limiting <zapi-rate-limit>` or an :ref:`unsuccessful
<zapi-unsuccessful-responses>` Zyte API response is received, no Scrapy
response object is built. Instead, a :ref:`retry policy <retry-policy>` is
followed, and if the policy retries are exhausted, a
:class:`zyte_api.RequestError` exception is raised.

That :class:`zyte_api.RequestError` exception is passed to the
``process_exception`` method of your :ref:`downloader middlewares
<topics-downloader-middleware>` and to your :ref:`spider errback
<topics-spiders>` if you defined one for the request. And you could have
:class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` retry that request
by adding :class:`zyte_api.RequestError` to the :setting:`RETRY_EXCEPTIONS
<scrapy:RETRY_EXCEPTIONS>` setting. But you are better off :ref:`relying on the
default retry policy or defining a custom retry policy <retry-policy>` instead.

.. _retry-policy:

Retry policy
============

Retry policies are a feature of the :ref:`Python Zyte API client library
<python-zyte-api:api>`, which scrapy-zyte-api uses underneath. See the
:ref:`upstream retry policy documentation <python-zyte-api:retry-policy>` to
learn about the default retry policy and how to create a custom retry policy,
including ready-to-use examples.

In scrapy-zyte-api, use the :setting:`ZYTE_API_RETRY_POLICY` setting or the
:reqmeta:`zyte_api_retry_policy` :attr:`Request.meta
<scrapy.http.Request.meta>` key to point to the import path of a retry policy
to use. For example, to switch to the :ref:`aggressive retry policy
<aggressive-retry-policy>`:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_RETRY_POLICY = "zyte_api.aggressive_retrying"
