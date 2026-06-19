.. _proxy-mode:

==========
Proxy mode
==========

Zyte API supports a :ref:`proxy mode <zapi-proxy>`, i.e. using Zyte API as a
proxy instead of as an HTTP API.

While the HTTP API is more powerful, proxy mode offers lower latency and
lower bandwidth usage.

:ref:`Manual requests <manual>` use the HTTP API by default. However,
:ref:`automap requests <automap>` compatible with proxy mode use it by default.

.. _request-mode:

Setting the request mode
========================

You can set the request mode to one of the following:

``"auto"``
    Use proxy mode if :ref:`eligible <proxy-mode-eligible>` or if the request
    carries ``Zyte-*`` headers, otherwise use the HTTP API.

``"http"``
    Use the HTTP API.

``"proxy"``
    Use proxy mode.

You can set the request mode with the :setting:`ZYTE_API_MODE` setting for
:ref:`automap requests <automap>`, or with the :reqmeta:`zyte_api_mode` request
metadata key for any request.

If neither :reqmeta:`zyte_api` nor :reqmeta:`zyte_api_automap` are set, using
:reqmeta:`zyte_api_mode` enables :ref:`automap <automap>` for the request.

If :reqmeta:`zyte_api_mode` is not used either, :ref:`proxy mode headers
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

.. _proxy-mode-provider:

scrapy-poet integration
=======================

Provider-generated requests respect :setting:`ZYTE_API_PROVIDER_MODE` (default
``"auto"``). For example, to send all provider requests via the HTTP API:

.. code-block:: python

    custom_settings = {
        "ZYTE_API_PROVIDER_MODE": "http",
    }

To override the mode for a single request, set
:reqmeta:`zyte_api_provider_mode` in the originating request:

.. code-block:: python

    yield Request(
        url,
        meta={"zyte_api_provider_mode": "http"},
    )
