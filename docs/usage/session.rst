.. _session:

=======================
Plugin-managed sessions
=======================

.. note::

    This page covers **plugin-managed sessions**, a session management feature
    built into scrapy-zyte-api. It does **not** cover the 2 session management
    features provided natively by Zyte API:

    -   :ref:`User-managed sessions <zapi-session-id>`, which give you full
        control over session management via the :http:`request:session` field.

    -   :ref:`Zyte-managed sessions <zapi-session-contexts>`, which let Zyte
        API handle session management for you via the
        :http:`request:sessionContext` field.

    You can use both of those Zyte API features directly from scrapy-zyte-api
    through their corresponding request parameters.

Plugin-managed sessions have an API similar to that of Zyte-managed sessions,
but are built on top of user-managed sessions.

Plugin-managed sessions offer some advantages over :ref:`Zyte-managed sessions
<zapi-session-contexts>`:

-   You can perform :ref:`session validity checks <session-check>`, so that the
    sessions of responses that do not pass those checks are refreshed, and the
    responses retried with a different session.

-   You can use arbitrary Zyte API parameters for :ref:`session initialization
    <session-init>`, beyond those that :http:`request:sessionContextParameters`
    supports.

-   You have granular control over the session pool size, max errors, etc. See
    :ref:`optimize-sessions` and :ref:`session-configs`.

However, plugin-managed sessions are not a replacement for :ref:`Zyte-managed
sessions <zapi-session-contexts>` or :ref:`user-managed sessions
<zapi-session-id>`:

-   :ref:`Zyte-managed sessions <zapi-session-contexts>` offer a longer life
    time than the :ref:`user-managed sessions <zapi-session-id>` that
    plugin-managed sessions use, so as long as you do not need one of the
    features of plugin-managed sessions, Zyte-managed sessions can be
    significantly more efficient (fewer session-initialization requests needed
    per crawl).

    Zyte API can also optimize Zyte-managed sessions based on the target
    website. With plugin-managed sessions, you need to :ref:`handle
    optimization yourself <optimize-sessions>`.

-   :ref:`User-managed sessions <zapi-session-id>` offer full control over
    session management, while plugin-managed sessions remove some of that
    control to provide an easier API for supported use cases.

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

For session management to work as expected, session requests must use a retry
policy that does not retry 520 and 521 responses, so that the session
management middleware can handle those instead.

520 and 521 are Zyte API status codes for download errors (e.g. connection
refused). When session management receives a 520 or 521 response, it counts it
as a session error, potentially discards the session (see
:setting:`ZYTE_API_SESSION_MAX_ERRORS`), and retries the request with a
different session. If the retry policy also retried 520 and 521 responses, it
would do so before the session middleware can swap the session, potentially
reusing the same problematic session for the retry.

scrapy-zyte-api handles this automatically: all requests that are assigned a
session get their :reqmeta:`zyte_api_retry_policy` request metadata key set
(via :func:`~dict.setdefault`) to the value of
:setting:`ZYTE_API_SESSION_RETRY_POLICY`.

Non-session requests continue to use :setting:`ZYTE_API_RETRY_POLICY` as usual,
unaffected by session management.

To override the retry policy for a specific request only, set
:reqmeta:`zyte_api_retry_policy` in the request metadata before the request
reaches the session middleware. The :func:`~dict.setdefault` call will not
override an already-set value.

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
    :ref:`Zyte-managed sessions <zapi-session-contexts>`, but it supports
    arbitrary Zyte API parameters instead of a specific subset.

    If it does not define a ``"url"``, the URL of the request :ref:`triggering
    a session initialization request <pool-size>` will be used.

-   When defining a :ref:`session config override <session-configs>`, you can
    customize the default and location-setting session initialization
    parameters through :meth:`~scrapy_zyte_api.SessionConfig.params`.

    :meth:`~scrapy_zyte_api.SessionConfig.location` can define a default
    location for its :ref:`session config override <session-configs>` to use
    when no location is specified otherwise.

-   When session initialization requires **a chain of multiple requests**
    (e.g. navigate to a page to get a token, then submit it), override
    :meth:`~scrapy_zyte_api.SessionConfig.init_session` in a :ref:`session
    config override <session-configs>`.

Precedence, from higher to lower, is:

#.  :reqmeta:`zyte_api_session_params`

#.  :reqmeta:`zyte_api_session_location`

#.  :setting:`ZYTE_API_SESSION_PARAMS`

#.  :setting:`ZYTE_API_SESSION_LOCATION`

#.  :meth:`~scrapy_zyte_api.SessionConfig.location`

#.  :meth:`~scrapy_zyte_api.SessionConfig.params`

.. note::

    The IP address assigned to a session is determined during session
    initialization and remains fixed for the lifetime of the session. Using a
    different :http:`request:geolocation` in a follow-up request that reuses a
    session is not supported and results in undefined behavior.

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

By default, if the :ref:`session initialization parameters <session-init>`
include :http:`actions <request:actions>`, and any of them has a ``returned``
status in the response (meaning it failed and stopped execution), the session
is discarded. Actions with ``onError`` set to ``"continue"`` that fail produce
a ``continued`` status instead, and do not cause the session to be discarded.
You can disable this behavior by setting
:setting:`ZYTE_API_SESSION_INIT_ACTION_FAILURE_INVALIDATES_SESSION` to
``False``.

In addition, if a location is defined through
:reqmeta:`zyte_api_session_location`, :setting:`ZYTE_API_SESSION_LOCATION` or
:meth:`~scrapy_zyte_api.SessionConfig.location`, and the ``setLocation`` action
is not available for a given website, the spider is closed with
``unsupported_set_location`` as the close reason; in that case, you should
define a proper :ref:`session initialization logic <session-init>` for requests
targeting that website.

For sessions initialized without actions, no action-based session check is
performed.

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
:setting:`ZYTE_API_SESSION_POOLS` setting allows defining different values
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

    On those websites, you can increase :setting:`ZYTE_API_SESSION_DELAY`,
    :setting:`ZYTE_API_SESSION_POOL_SIZE`, or both, to lower the rate of
    session reuse.

    Mind, however, that :ref:`user-managed sessions <zapi-session-id>` expire
    after 15 minutes since creation or 2 minutes since the last request (see
    :http:`request:session`). At a certain point, increasing
    :setting:`ZYTE_API_SESSION_POOL_SIZE` without increasing
    :setting:`CONCURRENT_REQUESTS <scrapy:CONCURRENT_REQUESTS>` and
    :setting:`CONCURRENT_REQUESTS_PER_DOMAIN
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
:http:`request:browserHtml` and :http:`request:actions`, :ref:`Zyte-managed
sessions <zapi-session-contexts>` might be a more cost-effective choice, as
they live much longer than :ref:`user-managed sessions <zapi-session-id>`.


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

.. _session-cookies-no-ip:

Because sessions tie cookies and IP addresses together, it is not possible to
use session cookie sharing while switching IP types or geolocations between
requests. For example, you cannot initialize a session with residential IPs and
then reuse its cookies with datacenter IPs.

To share cookies across requests that use different IP types or geolocations,
use :http:`response:responseCookies` from the first request as
:http:`request:requestCookies` in follow-up requests, instead of using
sessions.

Session retry policies
======================

The following retry policies are designed to work well with session management
(see :ref:`enable-sessions`). They are meant for
:setting:`ZYTE_API_SESSION_RETRY_POLICY`:

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

.. _session-troubleshooting:

Troubleshooting
===============

.. _session-troubleshooting-could-not-get-session-id:

RuntimeError: Could not get a session ID
----------------------------------------

If you see this exception, indicating that after a given number of attempts,
with a given minimum wait time between attempts, it was not possible to get a
session ID from the session rotation queue, consider the following
possibilities:

-   A bug in your session validation code may be causing it to return ``False``
    for a valid response.

    This is specially likely if you see this issue for very few, specific
    requests, while most requests work fine.

-   The values of the :setting:`ZYTE_API_SESSION_QUEUE_MAX_ATTEMPTS` and
    :setting:`ZYTE_API_SESSION_QUEUE_WAIT_TIME` settings may be too low for
    your scenario, in which case you can modify them accordingly.
