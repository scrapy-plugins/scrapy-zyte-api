.. _meta:

=================
Request.meta keys
=================

Keys that can be defined in :attr:`Request.meta <scrapy.http.Request.meta>` for
scrapy-zyte-api.

.. reqmeta:: zyte_api

zyte_api
========

Default: ``False``

See :ref:`manual`.


.. reqmeta:: zyte_api_automap

zyte_api_automap
================

Default: :setting:`ZYTE_API_TRANSPARENT_MODE` (``False``)

See :ref:`automap`.


.. reqmeta:: zyte_api_default_params

zyte_api_default_params
=======================

Default: ``True``

If set to ``False``, the values of :setting:`ZYTE_API_AUTOMAP_PARAMS` and
:setting:`ZYTE_API_DEFAULT_PARAMS` are ignored for this request.


.. reqmeta:: zyte_api_provider

zyte_api_provider
=================

Default: ``{}``

Sets Zyte API parameters to include into requests made by the :ref:`scrapy-poet
integration <scrapy-poet>`.

For example:

.. code-block:: python

    Request(
        "https://example.com",
        meta={
            "zyte_api_provider": {
                "requestCookies": [
                    {"name": "a", "value": "b", "domain": "example.com"},
                ],
            }
        },
    )

See also :setting:`ZYTE_API_PROVIDER_PARAMS`.


.. reqmeta:: zyte_api_retry_policy

zyte_api_retry_policy
=====================

Default: :setting:`ZYTE_API_RETRY_POLICY`
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


.. reqmeta:: zyte_api_session_enabled

zyte_api_session_enabled
=========================

Default: :setting:`ZYTE_API_SESSION_ENABLED`

Whether to send the request with a :ref:`plugin-managed session <session>`
(``True``) or not (``False``).

.. seealso:: :meth:`scrapy_zyte_api.SessionConfig.enabled`


.. reqmeta:: zyte_api_session_location

zyte_api_session_location
=========================

Default: ``{}``

See :ref:`session-init` for general information about location configuration
and parameter precedence.

Example:

.. code-block:: python

    Request(
        "https://example.com",
        meta={
            "zyte_api_session_location": {"postalCode": "10001"},
        },
    )


.. reqmeta:: zyte_api_session_params

zyte_api_session_params
=======================

Default: ``{}``

See :ref:`session-init` for general information about defining session
initialization parameters and parameter precedence.


.. reqmeta:: zyte_api_session_pool

zyte_api_session_pool
=====================

Default: ``""``

Determines the ID of the session pool to assign to the request, overriding the
:ref:`default pool assignment logic <session-pools>`.

Instead of a string, the value can be a :class:`dict` containing the pool ID
under the ``id`` key, and optionally a ``delay`` key with the minimum delay
between reuses of the sessions from that pool, and a ``size`` key with the
maximum number of sessions in that pool. For example:

.. code-block:: python

    {
        "id": "ecommerce.example",
        "delay": 2.0,
        "size": 16,
    }

The ``delay`` and ``size`` values returned take precedence over
:setting:`ZYTE_API_SESSION_DELAY` and :setting:`ZYTE_API_SESSION_POOL_SIZE` for
the specified pool ID, but do not override those defined in
:setting:`ZYTE_API_SESSION_POOLS`.

For any given pool ID, ``delay`` and ``size`` values are only taken into
account when the pool ID is first encountered. You cannot use this request
metadata key to change them at run time.

.. seealso:: :meth:`scrapy_zyte_api.SessionConfig.pool`
