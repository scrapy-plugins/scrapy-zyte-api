.. _settings:

========
Settings
========

:ref:`Settings <topics-settings>` for scrapy-zyte-api.

.. setting:: ZYTE_API_AUTO_FIELD_STATS

ZYTE_API_AUTO_FIELD_STATS
=========================

Default: ``False``

Enables stats that indicate which requested fields :ref:`obtained through
scrapy-poet integration <scrapy-poet>` come directly from
:ref:`zapi-extract`.

If for any request no page object class is used to override
:ref:`zapi-extract` fields for a given item type, the following stat is
set:

.. code-block:: python

    "scrapy-zyte-api/auto_fields/<item class import path>": "(all fields)"

.. note:: A literal ``(all fields)`` string is used as value, not a list with
    all fields.

If for any request a custom page object class is used to override some
:ref:`zapi-extract` fields, the following stat is set:

.. code-block:: python

    "scrapy-zyte-api/auto_fields/<override class import path>": (
        "<space-separated list of fields not overridden>"
    )

.. note:: :func:`zyte_common_items.fields.is_auto_field` is used to determine
    whether a field has been overridden or not.

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
API requests reaches it, with ``closespider_max_zapi_requests`` as the close
reason.

Note that requests with error responses that cannot be retried or exceed their
retry limit also count here.


.. setting:: ZYTE_API_PRESERVE_DELAY

ZYTE_API_PRESERVE_DELAY
=======================

Default: ``False if`` :setting:`AUTOTHROTTLE_ENABLED
<scrapy:AUTOTHROTTLE_ENABLED>` ``else True``

By default, requests for which use of scrapy-zyte-api is enabled get
``zyte-api@`` prepended to their download slot ID, and if
:setting:`AUTOTHROTTLE_ENABLED <scrapy:AUTOTHROTTLE_ENABLED>` is ``True``, the
corresponding download slot gets its download delay reset to 0. This nullifies
the effects of the :ref:`AutoThrottle extension <topics-autothrottle>` for Zyte
API requests, delegating throttling management to Zyte API.

If :setting:`AUTOTHROTTLE_ENABLED <scrapy:AUTOTHROTTLE_ENABLED>` is ``False``,
but you have a download delay set through :setting:`DOWNLOAD_DELAY
<scrapy:DOWNLOAD_DELAY>` and you do not want that delay to affect Zyte API
requests, set this setting to ``False``.

If you have :setting:`AUTOTHROTTLE_ENABLED <scrapy:AUTOTHROTTLE_ENABLED>`
enabled, and you want it to also work on Zyte API requests, set this setting to
``True``.


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


.. setting:: ZYTE_API_REFERRER_POLICY

ZYTE_API_REFERRER_POLICY
========================

Default: ``"no-referrer"``

:setting:`REFERRER_POLICY` to apply to Zyte API requests when using
:ref:`transparent mode <transparent>` or :ref:`automatic request parameters
<automap>`.

The :reqmeta:`referrer_policy` request metadata key takes precedence.

See :ref:`referer`.


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


.. setting:: ZYTE_API_SESSION_CHECKER

ZYTE_API_SESSION_CHECKER
========================

Default: ``None``

A :ref:`Scrapy component <topics-components>` (or its import path as a string)
that defines a ``check`` method.

If ``check`` returns ``True``, the response session is considered valid; if
``check`` returns ``False``, the response session is considered invalid, and
will be discarded. ``check`` can also raise a
:exc:`~scrapy.exceptions.CloseSpider` exception to close the spider.

If defined, the ``check`` method is called on every response that is using a
:ref:`session managed by scrapy-zyte-api <session>`. If not defined, the
default implementation checks the outcome of the ``setLocation`` action if
session initialization was location-based, as described in
:ref:`session-check`.

Example:

.. code-block:: python
    :caption: settings.py

    from scrapy import Request
    from scrapy.http.response import Response


    class MySessionChecker:

        def check(self, response: Response, request: Request) -> bool:
            return bool(response.css(".is_valid"))


    ZYTE_API_SESSION_CHECKER = MySessionChecker

Because the session checker is a Scrapy component, you can access the crawler
object, for example to read settings:

.. code-block:: python
    :caption: settings.py

    from scrapy import Request
    from scrapy.http.response import Response


    class MySessionChecker:

        @classmethod
        def from_crawler(cls, crawler):
            return cls(crawler)

        def __init__(self, crawler):
            location = crawler.settings["ZYTE_API_SESSION_LOCATION"]
            self.postal_code = location["postalCode"]

        def check(self, response: Response, request: Request) -> bool:
            return response.css(".postal_code::text").get() == self.postal_code


    ZYTE_API_SESSION_CHECKER = MySessionChecker


.. setting:: ZYTE_API_SESSION_ENABLED

ZYTE_API_SESSION_ENABLED
========================

Default: ``False``

Enables :ref:`scrapy-zyte-api session management <session>`.


.. setting:: ZYTE_API_SESSION_LOCATION

ZYTE_API_SESSION_LOCATION
=========================

Default: ``{}``

See :ref:`session-init` for general information about location configuration
and parameter precedence.

Example:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_SESSION_LOCATION = {"postalCode": "10001"}


.. setting:: ZYTE_API_SESSION_MAX_BAD_INITS

ZYTE_API_SESSION_MAX_BAD_INITS
==============================

Default: ``8``

The maximum number of :ref:`scrapy-zyte-api sessions <session>` per pool that
are allowed to fail their session check right after creation in a row. If the
maximum is reached, the spider closes with ``bad_session_inits`` as the close
reason.

To override this value for specific pools, use
:setting:`ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL`.


.. setting:: ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL

ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL
=======================================

Default: ``{}``

:class:`dict` where keys are :ref:`pool <session-pools>` IDs and values are
overrides of :setting:`ZYTE_API_SESSION_POOL_SIZE` for those pools.


.. setting:: ZYTE_API_SESSION_MAX_CHECK_FAILURES

ZYTE_API_SESSION_MAX_CHECK_FAILURES
===================================

Default: ``1``

Maximum number of :ref:`validity check <session-check>` failures allowed for
any given session before discarding the session.

You might want to increase this number if you find that a session may continue
to work even after it fails a validity check. See :ref:`optimize-sessions`.


.. setting:: ZYTE_API_SESSION_MAX_ERRORS

ZYTE_API_SESSION_MAX_ERRORS
===========================

Default: ``1``

Maximum number of :ref:`unsuccessful responses
<zapi-unsuccessful-responses>` allowed for any given session before
discarding the session.

You might want to increase this number if you find that a session may continue
to work even after an unsuccessful response. See :ref:`optimize-sessions`.

.. note:: This setting does not affect session checks
    (:setting:`ZYTE_API_SESSION_CHECKER`). See
    :setting:`ZYTE_API_SESSION_MAX_CHECK_FAILURES`.


.. setting:: ZYTE_API_SESSION_PARAMS

ZYTE_API_SESSION_PARAMS
=======================

Default: ``{}``

See :ref:`session-init` for general information about defining session
initialization parameters and parameter precedence.

Example:

.. code-block:: python
    :caption: settings.py

    ZYTE_API_SESSION_PARAMS = {
        "browserHtml": True,
        "actions": [
            {
                "action": "setLocation",
                "address": {"postalCode": "10001"},
            }
        ],
    }

.. tip:: The example above is equivalent to setting
    :setting:`ZYTE_API_SESSION_LOCATION` to ``{"postalCode": "10001"}``.


.. setting:: ZYTE_API_SESSION_POOL_SIZE

ZYTE_API_SESSION_POOL_SIZE
==========================

Default: ``8``

The maximum number of active :ref:`scrapy-zyte-api sessions <session>` to keep
per :ref:`pool <session-pools>`.

To override this value for specific pools, use
:setting:`ZYTE_API_SESSION_POOL_SIZES`.

Increase this number to lower the frequency with which requests are sent
through each session, which on some websites may increase the lifetime of each
session. See :ref:`optimize-sessions`.


.. setting:: ZYTE_API_SESSION_POOL_SIZES

ZYTE_API_SESSION_POOL_SIZES
===========================

Default: ``{}``

:class:`dict` where keys are :ref:`pool <session-pools>` IDs and values are
overrides of :setting:`ZYTE_API_SESSION_POOL_SIZE` for those pools.


.. setting:: ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS

ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS
===================================

Default: ``60``

scrapy-zyte-api maintains a rotation queue of ready-to-use sessions per
:ref:`pool <session-pools>`. At some points, the queue might be empty for a
given pool because all its sessions are in the process of being initialized or
refreshed.

If the queue is empty when trying to assign a session to a request,
scrapy-zyte-api will wait some time
(:setting:`ZYTE_API_SESSION_QUEUE_WAIT_TIME`), and then try to get a session
from the queue again.

Use this setting to configure the maximum number of attempts before giving up
and raising a :exc:`RuntimeError` exception.


.. setting:: ZYTE_API_SESSION_QUEUE_WAIT_TIME

ZYTE_API_SESSION_QUEUE_WAIT_TIME
===================================

Default: ``1.0``

Number of seconds to wait between attempts to get a session from a rotation
queue.

See :setting:`ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS` for details.


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
