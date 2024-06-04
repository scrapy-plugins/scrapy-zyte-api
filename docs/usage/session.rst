.. _session:

==================
Session management
==================

Zyte API provides powerful session APIs:

-   :ref:`Client-managed sessions <zyte-api-session-id>` give you full control
    over session management.

-   :ref:`Server-managed sessions <zyte-api-session-contexts>` let Zyte API
    handle session management for you.

When using scrapy-zyte-api, you can use these session APIs through the
corresponding Zyte API fields (:http:`request:session`,
:http:`request:sessionContext`).

However, scrapy-zyte-api also provides its own session API, which offers an API
similar to that of :ref:`server-managed sessions <zyte-api-session-contexts>`,
but built on top of :ref:`client-managed sessions <zyte-api-session-id>`, to
provide the best of both.

.. _enable-sessions:

Enabling session management
===========================

To enable session management for all requests, set
:setting:`ZYTE_API_SESSION_ENABLED` to ``True``. You can also toggle session
management on or off for specific requests using the
:reqmeta:`zyte_api_session_enabled` request metadata key.

By default, scrapy-zyte-api will maintain up to 8 sessions per domain, each
initialized with a :ref:`browser request <zyte-api-browser>` targeting the URL
of the first request that will use the session. Sessions will be automatically
rotated among requests, and refreshed as they expire or get banned.

For session management to work as expected, your
:setting:`ZYTE_API_RETRY_POLICY` should not retry 520 and 521 responses:

-   If you are using the default retry policy
    (:data:`~zyte_api.zyte_api_retrying`) or
    :data:`~zyte_api.aggressive_retrying`:

    -   If you are :ref:`using the add-on <config-addon>`, they are
        automatically replaced with a matching session-specific retry policy,
        either :data:`~scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY` or
        :data:`~scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY`.

    -   If you are not using the add-on, set :setting:`ZYTE_API_RETRY_POLICY`
        manually to either
        :data:`~scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY` or
        :data:`~scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY`. For example:

        .. code-block:: python
            :caption: settings.py

            ZYTE_API_RETRY_POLICY = "scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY"

-   If you are using a custom retry policy, modify it to not retry 520 and 521
    responses.

.. _session-init:

Initializing sessions
=====================

To change how sessions are initialized, you have the following options:

-   To run the ``setLocation`` :http:`action <request:actions>` for session
    initialization, use the :setting:`ZYTE_API_SESSION_LOCATION` setting or the
    :reqmeta:`zyte_api_session_location` request metadata key.

-   For session initialization with arbitrary Zyte API request fields, use the
    :setting:`ZYTE_API_SESSION_PARAMS` setting or the
    :reqmeta:`zyte_api_session_params` request metadata key.

-   To customize session initialization per request, define
    :meth:`~scrapy_zyte_api.SessionConfig.params` in a :ref:`session config
    override <session-configs>`.

.. _session-check:

Checking sessions
=================

Responses from a session can be checked for session validity. If a response
does not pass a session validity check, the session is discarded, and the
request is retried with a different session.

Session checking can be useful to work around scenarios where session
initialization fails, e.g. due to rendering issues, IP-geolocation mismatches,
A-B tests, etc. It can also help in cases where website sessions expire before
Zyte API sessions.

By default, for sessions that are initialized with a location, the outcome of
the ``setLocation`` action is checked. If the action fails, the session is
discarded. If the action is not even available for a given website, the spider
is closed with ``unsupported_set_location`` as the close reason, so that you
can set a proper :ref:`session initialization logic <session-init>` for
requests targeting that website.

For sessions initialized with arbitrary or no parameters, no session check is
performed, sessions are assumed to be fine until they expire or are banned.
That is so even if those arbitrary parameters include a ``setLocation`` action.

To implement your own code to check session responses and determine whether
their session should be kept or discarded, use the
:setting:`ZYTE_API_SESSION_CHECKER` setting.

If you need to check session validity for multiple websites, it is better to
define a separate :ref:`session config override <session-configs>` for each
website, each with its own implementation of
:meth:`~scrapy_zyte_api.SessionConfig.check`.

If your session checking implementation relies on the response body (e.g. it
uses CSS or XPath expressions), you should make sure that you are getting one,
which might not be the case if you are mostly using :ref:`Zyte API automatic
extraction <zyte-api-extract>`, e.g. when using :doc:`Zyte spider templates
<zyte-spider-templates:index>`. For example, you can use
:setting:`ZYTE_API_AUTOMAP_PARAMS` and :setting:`ZYTE_API_PROVIDER_PARAMS` to
force :http:`request:browserHtml` or :http:`request:httpResponseBody` to be set
on every Zyte API request:

.. code-block:: python
    :caption: setting.py

    ZYTE_API_AUTOMAP_PARAMS = {"browserHtml": True}
    ZYTE_API_PROVIDER_PARAMS = {"browserHtml": True}

.. _optimize-sessions:

Optimizing sessions
===================

For faster crawls and lower costs, specially where session initialization
requests are more expensive than session usage requests (e.g. because
initialization relies on ``browserHtml`` and usage relies on
``httpResponseBody``), you should try to make your sessions live as long as
possible before they are discarded.

Here are some things you can try:

-   On some websites, sending too many requests too fast through a session can
    cause the target website to ban that session.

    On those websites, you can increase the number of sessions in the pool
    (:setting:`ZYTE_API_SESSION_POOL_SIZE`). The more different sessions you
    use, the more slowly you send requests through each session.

    Mind, however, that :ref:`client-managed sessions <zyte-api-session-id>`
    expire after `15 minutes since creation or 2 minutes since the last request
    <https://docs.zyte.com/zyte-api/usage/reference.html#operation/extract/request/session>`_.
    At a certain point, increasing :setting:`ZYTE_API_SESSION_POOL_SIZE`
    without increasing :setting:`CONCURRENT_REQUESTS
    <scrapy:CONCURRENT_REQUESTS>` and :setting:`CONCURRENT_REQUESTS_PER_DOMAIN
    <scrapy:CONCURRENT_REQUESTS_PER_DOMAIN>` accordingly can be
    counterproductive.

-   By default, sessions are discarded as soon as an :ref:`unsuccessful
    response <zyte-api-unsuccessful-responses>` is received.

    However, on some websites sessions may remain valid even after a few
    unsuccessful responses. If that is the case, you might want to increase
    :setting:`ZYTE_API_SESSION_MAX_ERRORS` to require a higher number of
    unsuccessful responses before discarding a session.


.. _session-configs:

Overriding session configs
==========================

For spiders that target a single website, using settings and request metadata
keys for :ref:`session initialization <session-init>` and :ref:`session
checking <session-check>` should do the job. However, for broad crawls or
:doc:`multi-website spiders <zyte-spider-templates:index>`, you might want to
define different session configs for different websites.

The default session config is implemented by the
:class:`~scrapy_zyte_api.SessionConfig` class:

.. autoclass:: scrapy_zyte_api.SessionConfig
    :members:

To define a different session config for a given URL pattern, install
:doc:`web-poet <web-poet:index>` and define a subclass of
:class:`~scrapy_zyte_api.SessionConfig` decorated with
:func:`~scrapy_zyte_api.session_config`:

.. autofunction:: scrapy_zyte_api.session_config

.. _session-stats:

Session stats
=============

The following stats exist for scrapy-zyte-api session management:

``scrapy-zyte-api/sessions/pools/{pool}/init/check-failed``
    Number of times that a session from pool ``{pool}`` failed its session
    validation check right after initialization.

``scrapy-zyte-api/sessions/pools/{pool}/init/check-passed``
    Number of times that a session from pool ``{pool}`` passed its session
    validation check right after initialization.

``scrapy-zyte-api/sessions/pools/{pool}/init/failed``
    Number of times that initializing a session for pool ``{pool}`` resulted in
    an :ref:`unsuccessful response <zyte-api-unsuccessful-responses>`.

``scrapy-zyte-api/sessions/pools/{pool}/use/check-failed``
    Number of times that a response that used a session from pool ``{pool}``
    failed its session validation check.

``scrapy-zyte-api/sessions/pools/{pool}/use/check-passed``
    Number of times that a response that used a session from pool ``{pool}``
    passed its session validation check.

``scrapy-zyte-api/sessions/pools/{pool}/use/expired``
    Number of times that a session from pool ``{pool}`` expired.

``scrapy-zyte-api/sessions/pools/{pool}/use/failed``
    Number of times that a request that used a session from pool ``{pool}``
    got an :ref:`unsuccessful response <zyte-api-unsuccessful-responses>`.

Session retry policies
======================

The following retry policies are designed to work well with session management
(see :ref:`enable-sessions`):

.. autodata:: scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY
    :annotation:

.. autodata:: scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY
    :annotation:
