.. _session:

==================
Session management
==================

Zyte API provides powerful session APIs:

-   :ref:`Client-managed sessions <zapi-session-id>` give you full control
    over session management.

-   :ref:`Server-managed sessions <zapi-session-contexts>` let Zyte API
    handle session management for you.

When using scrapy-zyte-api, you can use these session APIs through the
corresponding Zyte API fields (:http:`request:session`,
:http:`request:sessionContext`).

However, scrapy-zyte-api also provides its own session management API, similar
to that of :ref:`server-managed sessions <zapi-session-contexts>`, but
built on top of :ref:`client-managed sessions <zapi-session-id>`.

scrapy-zyte-api session management offers some advantages over
:ref:`server-managed sessions <zapi-session-contexts>`:

-   You can perform :ref:`session validity checks <session-check>`, so that the
    sessions of responses that do not pass those checks are refreshed, and the
    responses retried with a different session.

-   You can use arbitrary Zyte API parameters for :ref:`session initialization
    <session-init>`, beyond those that :http:`request:sessionContextParameters`
    supports.

-   You have granular control over the session pool size, max errors, etc. See
    :ref:`optimize-sessions` and :ref:`session-configs`.

However, scrapy-zyte-api session management is not a replacement for
:ref:`server-managed sessions <zapi-session-contexts>` or
:ref:`client-managed sessions <zapi-session-id>`:

-   :ref:`Server-managed sessions <zapi-session-contexts>` offer a longer
    life time than the :ref:`client-managed sessions <zapi-session-id>`
    that scrapy-zyte-api session management uses, so as long as you do not need
    one of the scrapy-zyte-api session management features, server-managed
    sessions can be significantly more efficient (fewer total sessions needed
    per crawl).

    Zyte API can also optimize server-managed sessions based on the target
    website. With scrapy-zyte-api session management, you need to :ref:`handle
    optimization yourself <optimize-sessions>`.

-   :ref:`Client-managed sessions <zapi-session-id>` offer full control
    over session management, while scrapy-zyte-api session management removes
    some of that control to provide an easier API for supported use cases.

.. _enable-sessions:

Enabling session management
===========================

To enable session management for all requests, set
:setting:`ZYTE_API_SESSION_ENABLED` to ``True``. You can also toggle session
management on or off for specific requests using the
:reqmeta:`zyte_api_session_enabled` request metadata key, or override the
:meth:`~scrapy_zyte_api.SessionConfig.enabled` method of a :ref:`session config
override <session-configs>`.

.. _session-init-default:

By default, scrapy-zyte-api will maintain up to 8 sessions per domain, each
initialized with a :ref:`browser request <zapi-browser>` targeting the URL
of the first request that will use the session. Sessions are automatically
rotated among requests, and refreshed as they expire or get banned. You can
customize most of this logic through request metadata, settings and
:ref:`session config overrides <session-configs>`.

For session management to work as expected, your
:setting:`ZYTE_API_RETRY_POLICY` should not retry 520 and 521 responses:

-   If you are using the default retry policy
    (:data:`~zyte_api.zyte_api_retrying`) or
    :data:`~zyte_api.aggressive_retrying`:

    -   If you are :ref:`using the scrapy-zyte-api add-on <config-addon>`,
        these built-in retry policies are automatically replaced with a
        matching session-specific retry policy, either
        :data:`~scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY` or
        :data:`~scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY`.

    -   If you are not using the scrapy-zyte-api add-on, set
        :setting:`ZYTE_API_RETRY_POLICY` manually to either
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

To change the :ref:`default session initialization parameters
<session-init-default>`, you have the following options:

-   To initialize sessions with a given **location**, use the
    :setting:`ZYTE_API_SESSION_LOCATION` setting or the
    :reqmeta:`zyte_api_session_location` request metadata key.

    The value should be a dictionary with keys supported by the ``address``
    field of the ``setLocation`` :http:`action <request:actions>`, e.g.

    .. code-block:: python

        {
            "addressCountry": "US",
            "addressRegion": "NY",
            "postalCode": "10001",
            "streetAddress": "3 Penn Plz",
        }

    By default, the location is set using the ``setLocation``
    :http:`action <request:actions>`. A :ref:`session config override
    <session-configs>` can change that through
    :meth:`~scrapy_zyte_api.SessionConfig.params`.

-   For session initialization with **arbitrary Zyte API request fields**, use
    the :setting:`ZYTE_API_SESSION_PARAMS` setting or the
    :reqmeta:`zyte_api_session_params` request metadata key.

    It works similarly to :http:`request:sessionContextParams` from
    :ref:`server-managed sessions <zapi-session-contexts>`, but it supports
    arbitrary Zyte API parameters instead of a specific subset.

    If it does not define a ``"url"``, the URL of the request :ref:`triggering
    a session initialization request <pool-size>` will be used.

-   When defining a :ref:`session config override <session-configs>`, you can
    customize the default and location-setting session initialization
    parameters through :meth:`~scrapy_zyte_api.SessionConfig.params`.

    :meth:`~scrapy_zyte_api.SessionConfig.location` can define a default
    location for its :ref:`session config override <session-configs>` to use
    when no location is specified otherwise.

Precedence, from higher to lower, is:

#.  :reqmeta:`zyte_api_session_params`

#.  :reqmeta:`zyte_api_session_location`

#.  :setting:`ZYTE_API_SESSION_PARAMS`

#.  :setting:`ZYTE_API_SESSION_LOCATION`

#.  :meth:`~scrapy_zyte_api.SessionConfig.location`

#.  :meth:`~scrapy_zyte_api.SessionConfig.params`

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

By default, if a location is defined through
:reqmeta:`zyte_api_session_location`, :setting:`ZYTE_API_SESSION_LOCATION` or
:meth:`~scrapy_zyte_api.SessionConfig.location`, even if the parameters used
for session initialization actually come from
:reqmeta:`zyte_api_session_params` or :setting:`ZYTE_API_SESSION_LOCATION`, the
outcome of the first ``setLocation`` action used, if any, is checked. If the
action fails, the session is discarded. If the action is not even available for
a given website, the spider is closed with ``unsupported_set_location`` as the
close reason; in that case, you should define a proper :ref:`session
initialization logic <session-init>` for requests targeting that website.

For sessions initialized without a configured location, no session check is
performed, sessions are assumed to be fine until they expire or are banned.
That is so even if session initialization parameters include a ``setLocation``
action.

To implement your own code to check session responses and determine whether
their session should be kept or discarded, use the
:setting:`ZYTE_API_SESSION_CHECKER` setting. If you need to check session
validity for multiple websites, it is better to define a separate :ref:`session
config override <session-configs>` for each website, each with its own
implementation of :meth:`~scrapy_zyte_api.SessionConfig.check`.

The :reqmeta:`zyte_api_session_location` and :reqmeta:`zyte_api_session_params`
request metadata keys, if present in a request that :ref:`triggers a session
initialization request <pool-size>`, will be copied into the session
initialization request, so that they are available when
:setting:`ZYTE_API_SESSION_CHECKER` or
:meth:`~scrapy_zyte_api.SessionConfig.check` are called for a session
initialization request.

If your session checking implementation relies on the response body (e.g. it
uses CSS or XPath expressions), you should make sure that you are getting one,
which might not be the case if you are mostly using :ref:`Zyte API automatic
extraction <zapi-extract>`, e.g. when using :doc:`Zyte spider templates
<zyte-spider-templates:index>`. For example, you can use
:setting:`ZYTE_API_AUTOMAP_PARAMS` and :setting:`ZYTE_API_PROVIDER_PARAMS` to
force :http:`request:browserHtml` or :http:`request:httpResponseBody` to be set
on every Zyte API request:

.. code-block:: python
    :caption: setting.py

    ZYTE_API_AUTOMAP_PARAMS = {"browserHtml": True}
    ZYTE_API_PROVIDER_PARAMS = {"browserHtml": True}


.. _session-pools:

Managing pools
==============

scrapy-zyte-api can maintain multiple session pools.

By default, scrapy-zyte-api maintains a separate pool of sessions per domain.

If you use the :reqmeta:`zyte_api_session_params` or
:reqmeta:`zyte_api_session_location` request metadata keys, scrapy-zyte-api
will automatically use separate session pools within the target domain for
those parameters or locations. See :meth:`~scrapy_zyte_api.SessionConfig.pool`
for details.

If you want to customize further which pool is assigned to a given request,
e.g. to have the same pool for multiple domains or use different pools within
the same domain (e.g. for different URL patterns), you can either use the
:reqmeta:`zyte_api_session_pool` request metadata key or use the
:meth:`~scrapy_zyte_api.SessionConfig.pool` method of :ref:`session config
overrides <session-configs>`.

The :setting:`ZYTE_API_SESSION_POOL_SIZE` setting determines the desired number
of concurrent, active, working sessions per pool. The
:setting:`ZYTE_API_SESSION_POOL_SIZES` setting allows defining different values
for specific pools.

.. _pool-size:

The actual number of sessions created for a session pool depends on the number
of requests that ask for a session from that pool, and the life time of those
sessions:

-   When a request asks for a session from a given pool, if the session pool
    has not yet reached its desired pool size, a :ref:`session initialization
    request <session-init>` is triggered. If the session pool has been filled,
    an existing session is used instead.

-   When a response associated with a session pool indicates that the session
    expired, an error over the limit (see
    :setting:`ZYTE_API_SESSION_MAX_ERRORS`), or a :ref:`validity check
    <session-check>` failure over the limit (see
    :setting:`ZYTE_API_SESSION_MAX_CHECK_FAILURES`), a :ref:`session
    initialization request <session-init>` is triggered to replace that
    session in the session pool.

The session pool assigned to a request affects the :ref:`fingerprint
<fingerprint>` of the request. 2 requests with a different session pool ID are
considered different requests, i.e. not duplicate requests, even if they are
otherwise identical.


.. _optimize-sessions:

Optimizing sessions
===================

For faster crawls and lower costs, specially where session initialization
requests are more expensive than session usage requests (e.g. scenarios where
initialization relies on ``browserHtml`` while usage relies on
``httpResponseBody``), you should try to make your sessions live as long as
possible before they are discarded.

Here are some things you can try:

-   On some websites, sending too many requests too fast through a session can
    cause the target website to ban that session.

    On those websites, you can increase the number of sessions in the pool
    (:setting:`ZYTE_API_SESSION_POOL_SIZE`). The more different sessions you
    use, the more slowly you send requests through each session.

    Mind, however, that :ref:`client-managed sessions <zapi-session-id>`
    expire after `15 minutes since creation or 2 minutes since the last request
    <https://docs.zyte.com/zyte-api/usage/reference.html#operation/extract/request/session>`_.
    At a certain point, increasing :setting:`ZYTE_API_SESSION_POOL_SIZE`
    without increasing :setting:`CONCURRENT_REQUESTS
    <scrapy:CONCURRENT_REQUESTS>` and :setting:`CONCURRENT_REQUESTS_PER_DOMAIN
    <scrapy:CONCURRENT_REQUESTS_PER_DOMAIN>` accordingly can be
    counterproductive.

-   By default, sessions are discarded as soon as an :ref:`unsuccessful
    response <zapi-unsuccessful-responses>` is received or a :ref:`validity
    check <session-check>` is failed.

    However, on some websites sessions may remain valid even after a few
    unsuccessful responses or validity check failures. If that is the case, you
    might want to increase the corresponding setting,
    :setting:`ZYTE_API_SESSION_MAX_ERRORS` or
    :setting:`ZYTE_API_SESSION_MAX_CHECK_FAILURES`, to require a higher number
    of the corresponding outcome before discarding a session.

If you do not need :ref:`session checking <session-check>` and your
:ref:`initialization parameters <session-init>` are only
:http:`request:browserHtml` and :http:`request:actions`, :ref:`server-managed
sessions <zapi-session-contexts>` might be a more cost-effective choice, as
they live much longer than :ref:`client-managed sessions
<zapi-session-id>`.


.. _session-configs:

Overriding session configs
==========================

For spiders that target a single website, using settings and request metadata
keys for :ref:`session initialization <session-init>` and :ref:`session
checking <session-check>` should do the job. However, for broad-crawl spiders,
:doc:`multi-website spiders <zyte-spider-templates:index>`, to modify
session-using requests based on session initialization responses, or for code
reusability purposes, you might want to define different session configs for
different websites.

The default session config is implemented by the
:class:`~scrapy_zyte_api.SessionConfig` class:

.. autoclass:: scrapy_zyte_api.SessionConfig
    :members:

To define a different session config for a given URL pattern, install
:doc:`web-poet <web-poet:index>` and define a subclass of
:class:`~scrapy_zyte_api.SessionConfig` decorated with
:func:`~scrapy_zyte_api.session_config`:

.. autofunction:: scrapy_zyte_api.session_config

If you only need to override the :meth:`SessionConfig.check
<scrapy_zyte_api.SessionConfig.check>` or :meth:`SessionConfig.params
<scrapy_zyte_api.SessionConfig.params>` methods for scenarios involving a
location, you may subclass :class:`~scrapy_zyte_api.LocationSessionConfig`
instead:

.. autoclass:: scrapy_zyte_api.LocationSessionConfig
    :members: location_check, location_params

If in a session config implementation or in any other Scrapy component you need
to tell whether a request is a :ref:`session initialization request
<session-init>` or not, use :func:`~scrapy_zyte_api.is_session_init_request`:

.. autofunction:: scrapy_zyte_api.is_session_init_request

To get the session ID of a given request, use:

.. autofunction:: scrapy_zyte_api.get_request_session_id

Classes decorated with :func:`~scrapy_zyte_api.session_config` are registered
into :data:`~scrapy_zyte_api.session_config_registry`:

.. autodata:: scrapy_zyte_api.session_config_registry
    :annotation:

.. _session-cookies:

Cookie handling
===============

All requests involved in session management, both requests to initialize a
session and requests that are assigned a session, have their
:reqmeta:`dont_merge_cookies <scrapy:dont_merge_cookies>` request metadata key
set to ``True`` if not already defined. Each Zyte API session handles its own
cookies instead.

If you set :reqmeta:`dont_merge_cookies <scrapy:dont_merge_cookies>` to
``False`` in a request that uses a session, that request will include cookies
managed by Scrapy. However, session initialization requests will still have
:reqmeta:`dont_merge_cookies <scrapy:dont_merge_cookies>` set to ``True``, you
cannot override that.

To include cookies in session initialization requests, use
:http:`request:requestCookies` in :ref:`session initialization parameters
<session-init>`. But mind that those cookies are only set during that request,
:ref:`they are not added to the session cookie jar
<zapi-session-cookie-jar>`.


Session retry policies
======================

The following retry policies are designed to work well with session management
(see :ref:`enable-sessions`):

.. autodata:: scrapy_zyte_api.SESSION_DEFAULT_RETRY_POLICY
    :annotation:

.. autodata:: scrapy_zyte_api.SESSION_AGGRESSIVE_RETRY_POLICY
    :annotation:


Spider closers
==============

Session management can close your spider early in the following scenarios:

-   ``bad_session_inits``: Too many session initializations failed in a row for
    a given session pool.

    You can use the :setting:`ZYTE_API_SESSION_MAX_BAD_INITS` and
    :setting:`ZYTE_API_SESSION_MAX_BAD_INITS_PER_POOL` settings to adjust that
    maximum.

-   ``pool_error``: There was an error determining the session pool ID for some
    request.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.pool <scrapy_zyte_api.SessionConfig.pool>`; the
    logs should contain an error message with a traceback for such errors.

-   ``unsupported_set_location``: You used :setting:`ZYTE_API_SESSION_LOCATION`
    or :reqmeta:`zyte_api_session_location` to configure :ref:`session
    initialization <session-init>` with the ``setLocation`` action, but Zyte
    API does not yet support ``setLocation`` for the target website.

A custom :meth:`SessionConfig.check <scrapy_zyte_api.SessionConfig.check>`
implementation may also close your spider with a custom reason by raising a
:exc:`~scrapy.exceptions.CloseSpider` exception.


.. _session-stats:

Session stats
=============

The following stats exist for scrapy-zyte-api session management:

``scrapy-zyte-api/sessions/pools/{pool}/init/check-error``
    Number of times that a session for pool ``{pool}`` triggered an unexpected
    exception during its session validation check right after initialization.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.check <scrapy_zyte_api.SessionConfig.check>`; the
    logs should contain an error message with a traceback for such errors.

``scrapy-zyte-api/sessions/pools/{pool}/init/check-failed``
    Number of times that a session from pool ``{pool}`` failed its session
    validation check right after initialization.

``scrapy-zyte-api/sessions/pools/{pool}/init/check-passed``
    Number of times that a session from pool ``{pool}`` passed its session
    validation check right after initialization.

``scrapy-zyte-api/sessions/pools/{pool}/init/failed``
    Number of times that initializing a session for pool ``{pool}`` resulted in
    an :ref:`unsuccessful response <zapi-unsuccessful-responses>`.

``scrapy-zyte-api/sessions/pools/{pool}/init/param-error``
    Number of times that initializing a session for pool ``{pool}`` triggered
    an unexpected exception when obtaining the Zyte API parameters for session
    initialization.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.params <scrapy_zyte_api.SessionConfig.params>`; the
    logs should contain an error message with a traceback for such errors.

``scrapy-zyte-api/sessions/pools/{pool}/use/check-error``
    Number of times that a response that used a session from pool ``{pool}``
    triggered an unexpected exception during its session validation check.

    It is most likely the result of a bad implementation of
    :meth:`SessionConfig.check <scrapy_zyte_api.SessionConfig.check>`; the
    logs should contain an error message with a traceback for such errors.

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
    got an :ref:`unsuccessful response <zapi-unsuccessful-responses>`.

``scrapy-zyte-api/sessions/use/disabled``
    Number of processed requests for which session management was disabled.
