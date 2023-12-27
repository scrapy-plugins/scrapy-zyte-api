.. _meta:

=================
Request.meta keys
=================

Keys that can be defined in :attr:`Request.meta <scrapy.http.Request.meta>` for
scrapy-zyte-api.

.. _zyte_api:

zyte_api
========

Default: ``False``

See :ref:`manual`.


.. _zyte_api_automap:

zyte_api_automap
================

Default: :ref:`ZYTE_API_TRANSPARENT_MODE` (``False``)

See :ref:`automap`.


.. _zyte_api_default_params_meta:

zyte_api_default_params
=======================

Default: ``True``

If set to ``False``, the values of :ref:`ZYTE_API_AUTOMAP_PARAMS` and
:ref:`ZYTE_API_DEFAULT_PARAMS` are ignored for this request.


.. _zyte_api_retry_policy_meta:

zyte_api_retry_policy
=====================

Default: :ref:`ZYTE_API_RETRY_POLICY`
(:data:`zyte_api.aio.retry.zyte_api_retrying`)

Determines the retry policy for Zyte API requests used to fulfill this request.

It must be a :class:`tenacity.AsyncRetrying` subclass or its import path as a
string.

.. note:: If you need your request to be serializable, e.g. to use
    :class:`~scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware`, you
    must specify the import path of your retry policy class as a string,
    because `retry policies are not serializable
    <https://github.com/jd/tenacity/issues/147>`_.

See :ref:`retry`.
