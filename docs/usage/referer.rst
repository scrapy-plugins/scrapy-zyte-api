.. _referer:

==================
The Referer header
==================

By default, Scrapy automatically sets a `Referer header`_ on every request
yielded from a callback (see the
:class:`~scrapy.spidermiddlewares.referer.RefererMiddleware`).

However, when using :ref:`transparent mode <transparent>` or :ref:`automatic
request parameters <automap>`, this behavior is disabled by default for Zyte
API requests, and when using :ref:`manual request parameters <manual>`, all
request headers are always ignored for Zyte API requests.

.. _Referer header: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referer

Why is it disabled by default?
==============================

A misuse of the ``Referer`` header can increase the risk of :ref:`bans <bans>`.

By *not* setting the header, your Zyte API requests let Zyte API choose which
value to use, if any, to minimize bans.

If you *do* set the header, while Zyte API might still ignore your value to
avoid bans, it may also keep your value regardless of its impact on bans.

How to override?
================

To set the header anyway when using :ref:`transparent mode <transparent>` or
:ref:`automatic request parameters <automap>`, do any of the following:

-  Set the :setting:`ZYTE_API_REFERRER_POLICY` setting or the
   :reqmeta:`referrer_policy` request metadata key to ``"scrapy-default"`` or
   to some other value supported by the :setting:`REFERRER_POLICY` setting.

-  Set the header through the :setting:`DEFAULT_REQUEST_HEADERS` setting or
   the :attr:`Request.headers <scrapy.http.Request.headers>` attribute.

-  Set the header through the :http:`request:customHttpRequestHeaders` field
   (for :ref:`HTTP requests <zapi-http>`) or the :http:`request:requestHeaders`
   field (for :ref:`browser requests <zapi-browser>`) through the
   :setting:`ZYTE_API_AUTOMAP_PARAMS` setting or the
   :reqmeta:`zyte_api_automap` request metadata key.

When using :ref:`manual request parameters <manual>`, you always need to set
the header through the :http:`request:customHttpRequestHeaders` or
:http:`request:requestHeaders` field through the
:setting:`ZYTE_API_DEFAULT_PARAMS` setting or the :reqmeta:`zyte_api` request
metadata key.
