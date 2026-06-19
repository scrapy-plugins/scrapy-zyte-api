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
    :setting:`ZYTE_API_TRANSPORT` or :setting:`ZYTE_API_PROVIDER_TRANSPORT`
    setting, or the :reqmeta:`zyte_api_transport` or
    :reqmeta:`zyte_api_provider_transport` request metadata key, to ``"auto"``
    or ``"proxy"``.

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
:ref:`automap <automap>` and proxy mode for the request.

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
-   ``javascript: True`` *(proxy always enables JavaScript)*
-   ``[experimental.]requestCookies`` / ``[experimental.]responseCookies``

Extraction parameters (``product``, ``article``, ``actions``, ``screenshot``,
``networkCapture``, and so on) are **not** supported by the proxy endpoint and
force the HTTP API.

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
