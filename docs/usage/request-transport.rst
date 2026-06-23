.. _request-transport:

=================
Request transport
=================

Zyte API supports 2 different APIs to send requests, an HTTP API and a
:ref:`proxy mode <zapi-proxy>`.

While the HTTP API is more powerful, proxy mode offers lower latency and lower
bandwidth usage.

.. _experimental-proxy:

.. note:: Proxy mode support is **experimental**.

    While proxy mode support is experimental, scrapy-zyte-api never sends a
    request through proxy mode unless you opt in, by setting the
    :setting:`ZYTE_API_TRANSPORT`, :setting:`ZYTE_API_PROVIDER_TRANSPORT` or
    :setting:`ZYTE_API_SESSION_TRANSPORT` setting, or the
    :reqmeta:`zyte_api_transport`, :reqmeta:`zyte_api_provider_transport` or
    :reqmeta:`zyte_api_session_transport` request metadata key, to ``"auto"``
    or ``"proxy"``. For requests routed through proxy mode because they carry
    ``Zyte-*`` headers (see :ref:`header-transport`), you can instead set the
    :setting:`ZYTE_API_HEADER_TRANSPORT_ENABLED` setting to ``True``.

    When a request would be sent through proxy mode automatically once the
    feature is no longer experimental, scrapy-zyte-api sends it through the
    HTTP API instead and logs a warning (once) inviting you to opt in. To opt
    in, set the corresponding setting or metadata key above to ``"auto"`` or
    ``"proxy"``. To keep using the HTTP API and silence the warning, set it to
    ``"http"`` instead.

    If you enable proxy mode and run into any issues, please `report them
    <https://github.com/scrapy-plugins/scrapy-zyte-api/issues>`_.

:ref:`Manual requests <manual>` use the HTTP API by default. However,
:ref:`automap requests <automap>` compatible with proxy mode will
:ref:`eventually <experimental-proxy>` use it by default instead.

Setting the request transport
=============================

You can set the request transport to one of the following:

.. _auto-transport:

``"auto"``
    Use proxy mode if :ref:`eligible <proxy-mode-eligible>` or if the request
    carries ``Zyte-*`` headers, otherwise use the HTTP API.

.. _http-transport:

``"http"``
    Use the HTTP API.

.. _proxy-transport:

``"proxy"``
    Use proxy mode.

You can set the request transport with the :setting:`ZYTE_API_TRANSPORT`
setting for :ref:`automap requests <automap>`, or with the
:reqmeta:`zyte_api_transport` request metadata key for any request.

If neither :reqmeta:`zyte_api` nor :reqmeta:`zyte_api_automap` are set, using
:reqmeta:`zyte_api_transport` enables :ref:`automap <automap>` for the request.

If :reqmeta:`zyte_api_transport` is not used either, :ref:`proxy mode headers
<zapi-proxy>` in :attr:`Request.headers <scrapy.http.Request.headers>` enable
:ref:`automap <automap>` and proxy mode for the request, as long as the
:setting:`ZYTE_API_HEADER_TRANSPORT_ENABLED` setting is ``True``.

.. _header-transport:

Header-based transport
======================

By default, a request that carries ``Zyte-*`` (:ref:`proxy mode <zapi-proxy>`)
headers is automatically sent through Zyte API in :ref:`proxy mode
<proxy-transport>`, even if it does not set :reqmeta:`zyte_api`,
:reqmeta:`zyte_api_automap` or :reqmeta:`zyte_api_transport`.

.. note:: While :ref:`proxy mode is experimental <experimental-proxy>`, a
    request that is eligible for proxy mode only because it carries ``Zyte-*``
    headers is sent through the HTTP API instead, and a warning is logged. To
    send such requests through proxy mode, set
    :setting:`ZYTE_API_HEADER_TRANSPORT_ENABLED` to ``True``; to ignore those
    headers instead, set it to ``False``. Either value silences the warning.

This is controlled by the :setting:`ZYTE_API_HEADER_TRANSPORT_ENABLED` setting.
Its default value is ``True``, unless `scrapy-zyte-smartproxy
<https://scrapy-zyte-smartproxy.readthedocs.io/en/latest/>`_ is enabled for the
project (through its ``ZYTE_SMARTPROXY_ENABLED`` setting or its
``zyte_smartproxy_enabled`` spider attribute), in which case it defaults to
``False`` so that ``Zyte-*`` headers can be intended for scrapy-zyte-smartproxy
requests.

Set :setting:`ZYTE_API_HEADER_TRANSPORT_ENABLED` to ``False`` to handle other
scenarios where ``Zyte-*`` headers should not, on their own, route a request
through Zyte API. Even then, you can still opt a request into Zyte API
explicitly through :reqmeta:`zyte_api`, :reqmeta:`zyte_api_automap` or
:reqmeta:`zyte_api_transport`.

.. _proxy-mode-eligible:

Proxy-eligible parameters
=========================

A request is eligible for proxy mode when **all** of its Zyte API parameters
belong to the set of proxy-supported parameters:

-   ``url``
-   ``httpResponseBody`` / ``httpResponseHeaders``
-   ``browserHtml``
-   ``device``, ``geolocation``, ``ipType``
-   ``session``
-   ``jobId``, ``cookieManagement``, ``followRedirect``, ``tags``
-   ``requestHeaders``, ``customHttpRequestHeaders``
-   ``httpRequestBody``, ``httpRequestMethod``
-   ``javascript: True`` *(for browser requests proxy mode always enables
    JavaScript and it cannot be disabled; for non-browser requests the toggle
    is a no-op)*
-   ``[experimental.]requestCookies`` / ``[experimental.]responseCookies``,
    **except when browser rendering** (``browserHtml``) **is used** (see below)

Extraction parameters (``product``, ``article``, ``actions``, ``screenshot``,
``networkCapture``, and so on) are **not** supported by the proxy endpoint and
force the HTTP API.

.. _proxy-cookies-browser:

Cookies and browser rendering
-----------------------------

The cookie parameters :http:`request:requestCookies` and
:http:`request:responseCookies` (and their ``experimental.*`` forms) are
proxy-eligible only for plain HTTP requests, not when browser rendering
(``browserHtml``) is used. Proxy mode cannot represent the browser cookie jar:

-   Request cookies can only be sent to the proxy as a flat ``Cookie`` header,
    which loses the per-cookie ``domain``, ``path`` and flags that the browser
    cookie jar relies on during rendering.

-   Response cookies can only be recovered from the main response's
    ``Set-Cookie`` header, which misses cookies set later during rendering
    (e.g. via JavaScript or redirects). The HTTP API instead returns the
    *final* cookies in its ``responseCookies`` field.

As a result, a request that combines ``browserHtml`` with any of these cookie
parameters is **not** eligible for proxy mode: an ``"auto"`` request falls back
to the HTTP API, while a request that explicitly uses :ref:`proxy mode
<proxy-transport>` raises an error. Use the :ref:`HTTP API <http-transport>`
for these requests.

.. _request-transport-provider:

scrapy-poet integration
=======================

Provider-generated requests respect :setting:`ZYTE_API_PROVIDER_TRANSPORT`
(default ``"auto"``). For example, to send all provider requests via the HTTP
API:

.. code-block:: python

    custom_settings = {
        "ZYTE_API_PROVIDER_TRANSPORT": "http",
    }

To override the transport for a single request, set
:reqmeta:`zyte_api_provider_transport` in the originating request:

.. code-block:: python

    yield Request(
        url,
        meta={"zyte_api_provider_transport": "http"},
    )

.. _request-transport-session:

Sessions
========

:ref:`Plugin-managed sessions <session>` work with proxy mode. Because a Zyte
API session is identified only by its id, it can be initialized through one
transport and used through another:

-   The transport used to **use** a session follows the regular request
    transport of the request being sent (:setting:`ZYTE_API_TRANSPORT` or
    :reqmeta:`zyte_api_transport`).

-   The transport used to **initialize** a session is controlled separately, by
    the :setting:`ZYTE_API_SESSION_TRANSPORT` setting (default ``"auto"``) or
    the :reqmeta:`zyte_api_session_transport` request metadata key. A dedicated
    setting is needed because :ref:`session initialization <session-init>`
    requests are manual (:reqmeta:`zyte_api`) requests, which always default to
    the HTTP API.

For example, to send all session traffic (initialization and use) through proxy
mode:

.. code-block:: python

    custom_settings = {
        "ZYTE_API_TRANSPORT": "proxy",
        "ZYTE_API_SESSION_TRANSPORT": "proxy",
    }
