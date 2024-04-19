.. _settings:

========
Settings
========

:ref:`Settings <topics-settings>` for scrapy-zyte-api.

.. setting:: ZYTE_API_AUTOMAP_PARAMS

ZYTE_API_AUTOMAP_PARAMS
=======================

Default: ``{}``

:class:`dict` of parameters to be combined with :ref:`automatic request
parameters <automap>`.

These parameters are merged with :reqmeta:`zyte_api_automap` parameters.
:reqmeta:`zyte_api_automap` parameters take precedence.

This setting has no effect on requests with :ref:`manual request parameters
<manual>`.

When using :ref:`transparent mode <transparent>`, be careful of which
parameters you define in this setting. In transparent mode, all Scrapy requests
go through Zyte API, even requests that Scrapy sends automatically, such as
those for ``robots.txt`` files when :setting:`ROBOTSTXT_OBEY
<scrapy:ROBOTSTXT_OBEY>` is ``True``, or those for sitemaps when using
:class:`~scrapy.spiders.SitemapSpider`. Certain parameters, like
:http:`request:browserHtml` or :http:`request:screenshot`, are not meant to be
used for every single request.

If :reqmeta:`zyte_api_default_params` in :attr:`Request.meta
<scrapy.http.Request.meta>` is set to ``False``, this setting is ignored for
that request.

See :ref:`default`.


.. setting:: ZYTE_API_BROWSER_HEADERS

ZYTE_API_BROWSER_HEADERS
========================

Default: ``{"Referer": "referer"}``

Determines headers that *can* be mapped as :http:`request:requestHeaders`.

It is a :class:`dict`, where keys are header names and values are the key that
represents them in :http:`request:requestHeaders`.


.. setting:: ZYTE_API_COOKIE_MIDDLEWARE

ZYTE_API_COOKIE_MIDDLEWARE
==========================

Default: :class:`scrapy.downloadermiddlewares.cookies.CookiesMiddleware`

If you are using a custom downloader middleware to handle request cookie jars,
you can point this setting to its import path to make scrapy-zyte-api work with
it.

Your cookie downloader middleware must have a ``jars`` property with the same
signature as in the built-in Scrapy downloader middleware for cookie handling.


.. setting:: ZYTE_API_DEFAULT_PARAMS

ZYTE_API_DEFAULT_PARAMS
=======================

Default: ``{}``

:class:`dict` of parameters to be combined with :ref:`manual request parameters
<manual>`.

You may set :reqmeta:`zyte_api` to an empty :class:`dict` to only use the
parameters defined here for that request.

These parameters are merged with :reqmeta:`zyte_api` parameters.
:reqmeta:`zyte_api` parameters take precedence.

This setting has no effect on requests with :ref:`automatic request parameters
<automap>`.

If :reqmeta:`zyte_api_default_params` in :attr:`Request.meta
<scrapy.http.Request.meta>` is set to ``False``, this setting is ignored for
that request.

See :ref:`default`.


.. setting:: ZYTE_API_ENABLED

ZYTE_API_ENABLED
================

Default: ``True``

Can be set to ``False`` to disable scrapy-zyte-api.


.. setting:: ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED

ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED
=====================================

Default: ``False``

See :ref:`request-automatic`.


.. setting:: ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS

ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS
=============================================

Default: :class:`scrapy_poet.ScrapyPoetRequestFingerprinter` if scrapy-poet is
installed, else :class:`scrapy.utils.request.RequestFingerprinter`

:ref:`Request fingerprinter <request-fingerprints>` to for requests that do not
go through Zyte API. See :ref:`fingerprint`.


.. setting:: ZYTE_API_KEY

ZYTE_API_KEY
============

Default: ``None``

Your `Zyte API key`_.

.. _Zyte API key: https://app.zyte.com/o/zyte-api/api-access

You can alternatively define an environment variable with the same name.

.. tip:: On :ref:`Scrapy Cloud <scrapy-cloud>`, this setting is defined
    automatically.


.. setting:: ZYTE_API_LOG_REQUESTS

ZYTE_API_LOG_REQUESTS
=====================

Default: ``False``

Set this to ``True`` and :setting:`LOG_LEVEL <scrapy:LOG_LEVEL>` to ``"DEBUG"``
to enable the logging of debug messages that indicate the JSON object sent on
every Zyte API request.

For example::

   Sending Zyte API extract request: {"url": "https://example.com", "httpResponseBody": true}

See also: :setting:`ZYTE_API_LOG_REQUESTS_TRUNCATE`.


.. setting:: ZYTE_API_LOG_REQUESTS_TRUNCATE

ZYTE_API_LOG_REQUESTS_TRUNCATE
==============================

Default: ``64``

Determines the maximum length of any string value in the JSON object logged
when :setting:`ZYTE_API_LOG_REQUESTS` is enabled, excluding object keys.

To disable truncation, set this to ``0``.


.. setting:: ZYTE_API_MAX_COOKIES

ZYTE_API_MAX_COOKIES
====================

Default: ``100``

If the cookies to be set during :ref:`request mapping <request>` exceed this
limit, a warning is logged, and only as many cookies as the limit allows are
set for the target request.

To silence this warning, set :http:`request:experimental.requestCookies`
manually, e.g. to an empty :class:`dict`.

Alternatively, if :http:`request:experimental.requestCookies` starts supporting
more than 100 cookies, update this setting accordingly.


.. setting:: ZYTE_API_MAX_REQUESTS

ZYTE_API_MAX_REQUESTS
=====================

Default: ``None``

When set to an integer value > 0, the spider will close when the number of Zyte
API requests reaches it.

Note that requests with error responses that cannot be retried or exceed their
retry limit also count here.


.. setting:: ZYTE_API_PROVIDER_PARAMS

ZYTE_API_PROVIDER_PARAMS
========================

Default: ``{}``

Defines additional request parameters to use in Zyte API requests sent by the
:ref:`scrapy-poet integration <scrapy-poet>`.

For example:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_PROVIDER_PARAMS = {
        "requestCookies": [
            {"name": "a", "value": "b", "domain": "example.com"},
        ],
    }


.. setting:: ZYTE_API_RETRY_POLICY

ZYTE_API_RETRY_POLICY
=====================

Default: ``"zyte_api.aio.retry.zyte_api_retrying"``

Determines the retry policy for Zyte API requests.

It must be a string with the import path of a :class:`tenacity.AsyncRetrying`
subclass.

.. note:: :ref:`Settings <topics-settings>` must be :mod:`picklable <pickle>`,
    and `retry policies are not <https://github.com/jd/tenacity/issues/147>`_,
    so you cannot assign a retry policy class directly to this setting, you
    must use their import path as a string instead.

See :ref:`retry`.


.. setting:: ZYTE_API_SKIP_HEADERS

ZYTE_API_SKIP_HEADERS
=====================

Default: ``["Cookie"]``

Determines headers that must *not* be mapped as
:http:`request:customHttpRequestHeaders`.


.. setting:: ZYTE_API_TRANSPARENT_MODE

ZYTE_API_TRANSPARENT_MODE
=========================

Default: ``False``

See :ref:`transparent`.


.. setting:: ZYTE_API_USE_ENV_PROXY

ZYTE_API_USE_ENV_PROXY
======================

Default: ``False``

Set to ``True`` to make Zyte API requests respect system proxy settings. See
:ref:`proxy`.
