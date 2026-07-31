.. _request:

===============
Request mapping
===============

When you enable automatic request parameter mapping, be it through
:ref:`transparent mode <transparent>` or :ref:`for a specific request
<automap>`, some Zyte API parameters are :ref:`chosen automatically for you
<request-automatic>`, and you can then :ref:`change them further
<request-change>` if you wish.

.. _request-automatic:

Automatic mapping
=================

-   :attr:`Request.url <scrapy.http.Request.url>` becomes :http:`request:url`,
    same as in :ref:`requests with manual parameters <manual>`.

-   If :attr:`Request.method <scrapy.http.Request.method>` is something other
    than ``"GET"``, it becomes :http:`request:httpRequestMethod`.

-   :attr:`Request.body <scrapy.http.Request.body>` becomes
    :http:`request:httpRequestBody`.

.. _request-header-mapping:

-   :attr:`Request.headers <scrapy.http.Request.headers>` become
    :http:`request:customHttpRequestHeaders` for HTTP requests and
    :http:`request:requestHeaders` for browser requests. See
    :ref:`header-mapping` and :ref:`request-unsupported` for details.

    If :http:`request:serp` is enabled, request header mapping is disabled.

-   If :setting:`ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED` is ``True``,
    :setting:`COOKIES_ENABLED <scrapy:COOKIES_ENABLED>` is ``True`` (default),
    and :attr:`Request.meta <scrapy.http.Request.meta>` does not set
    :reqmeta:`dont_merge_cookies <scrapy:dont_merge_cookies>` to ``True``:

    -   :http:`request:experimental.responseCookies` becomes ``True``.

    -   Cookies from the :reqmeta:`cookiejar <scrapy:cookiejar>` become
        :http:`request:experimental.requestCookies`.

        All cookies from the cookie jar are set, regardless of their cookie
        domain. This is because Zyte API requests may involve requests to
        different domains (e.g. when following cross-domain redirects, or
        during browser rendering).

        See also: :setting:`ZYTE_API_MAX_COOKIES`,
        :setting:`ZYTE_API_COOKIE_MIDDLEWARE`.

-   :http:`request:httpResponseBody` and :http:`request:httpResponseHeaders`
    are set to ``True``.

    This is subject to change without prior notice in future versions of
    scrapy-zyte-api, so please account for the following:

    -   If you are requesting a binary resource, such as a PDF file or an
        image file, set :http:`request:httpResponseBody` to ``True`` explicitly
        in your requests:

        .. code-block:: python

            Request(
                url="https://toscrape.com/img/zyte.png",
                meta={
                    "zyte_api_automap": {"httpResponseBody": True},
                },
            )

        In the future, we may stop setting :http:`request:httpResponseBody` to
        ``True`` by default, and instead use a different, new Zyte API
        parameter that only works for non-binary responses (e.g. HMTL, JSON,
        plain text).

    -   If you need to access response headers, be it through
        :attr:`response.headers <scrapy_zyte_api.responses.ZyteAPIResponse.headers>`
        or through
        :attr:`response.raw_api_response["httpResponseHeaders"] <scrapy_zyte_api.responses.ZyteAPIResponse.raw_api_response>`,
        set :http:`request:httpResponseHeaders` to ``True`` explicitly in your
        requests:

        .. code-block:: python

            Request(
                url="https://toscrape.com/",
                meta={
                    "zyte_api_automap": {"httpResponseHeaders": True},
                },
            )

        At the moment scrapy-zyte-api requests response headers because some
        response headers are necessary to properly decode the response body as
        text. In the future, Zyte API may be able to handle this decoding
        automatically, so scrapy-zyte-api would stop setting
        :http:`request:httpResponseHeaders` to ``True`` by default.

For example, the following Scrapy request:

.. code-block:: python

    Request(
        method="POST",
        url="https://httpbin.org/anything",
        headers={"Content-Type": "application/json"},
        body=b'{"foo": "bar"}',
        cookies={"a": "b"},
    )

Results in a request to the Zyte API data extraction endpoint with the
following parameters:

.. code-block:: javascript

    {
        "customHttpRequestHeaders": [
            {
                "name": "Content-Type",
                "value": "application/json"
            }
        ],
        "experimental": {
            "requestCookies": [
                {
                    "name": "a",
                    "value": "b",
                    "domain": ""
                }
            ],
            "responseCookies": true
        },
        "httpResponseBody": true,
        "httpResponseHeaders": true,
        "httpRequestBody": "eyJmb28iOiAiYmFyIn0=",
        "httpRequestMethod": "POST",
        "url": "https://httpbin.org/anything"
    }


.. _header-mapping:

Header mapping
==============

When mapping headers, some headers are dropped based on the values of the
:setting:`ZYTE_API_SKIP_HEADERS` and :setting:`ZYTE_API_BROWSER_HEADERS`
settings. Their default values cause the drop of headers not supported by Zyte
API.

Even if not defined in :setting:`ZYTE_API_SKIP_HEADERS`, additional headers may
be dropped from HTTP requests (:http:`request:customHttpRequestHeaders`):

-   The ``Accept`` and ``Accept-Language`` headers are dropped if their values
    are not user-defined, i.e. they come from the :ref:`default global value
    <populating-settings>` (setting :meth:`priority
    <scrapy.settings.BaseSettings.getpriority>` of 0) of the
    :setting:`DEFAULT_REQUEST_HEADERS <scrapy:DEFAULT_REQUEST_HEADERS>`
    setting.

-   The ``Accept-Encoding`` header is dropped if its value is not user-defined,
    i.e. it was set by the
    :class:`~scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware`.

-   The ``User-Agent`` header is dropped if its value is not user-defined, i.e.
    it comes from the :ref:`default global value <populating-settings>`
    (setting :meth:`priority <scrapy.settings.BaseSettings.getpriority>` of 0)
    of the :setting:`USER_AGENT <scrapy:USER_AGENT>` setting.

To force the mapping of these headers, define the corresponding setting
(if any), set them in the :setting:`DEFAULT_REQUEST_HEADERS
<scrapy:DEFAULT_REQUEST_HEADERS>` setting, or set them in
:attr:`Request.headers <scrapy.http.Request.headers>` from a spider callback.
They will be mapped even if defined with their default value.

Headers will also be mapped if set to a non-default value elsewhere, e.g. in a
custom downloader middleware, as long as it is done before the scrapy-zyte-api
downloader middleware, which is responsible for the mapping, processes the
request. Here “before” means a lower value than ``633`` in the
:setting:`DOWNLOADER_MIDDLEWARES <scrapy:DOWNLOADER_MIDDLEWARES>` setting.

Similarly, you can add any of those headers to the
:setting:`ZYTE_API_SKIP_HEADERS` setting to prevent their mapping.

Also note that Scrapy sets the ``Referer`` header by default in all requests
that come from spider callbacks. To unset the header on a given request, set
the header value to ``None`` on that request. To unset it from all requests,
set the :setting:`REFERER_ENABLED <scrapy:REFERER_ENABLED>` setting to
``False``. To unset it only from Zyte API requests, add it to the
:setting:`ZYTE_API_SKIP_HEADERS` setting and remove it from the
:setting:`ZYTE_API_BROWSER_HEADERS` setting.


.. _request-unsupported:

Unsupported scenarios
=====================

To maximize support for potential future changes in Zyte API, automatic
request parameter mapping allows some parameter values and parameter
combinations that Zyte API does not currently support, and may never support:

-   :attr:`Request.method <scrapy.http.Request.method>` becomes
    :http:`request:httpRequestMethod` even for unsupported
    :http:`request:httpRequestMethod` values, and even if
    :http:`request:httpResponseBody` is unset.

-   You can set :http:`request:customHttpRequestHeaders` or
    :http:`request:requestHeaders` to ``True`` to force their mapping from
    :attr:`Request.headers <scrapy.http.Request.headers>` in scenarios where
    they would not be mapped otherwise.

    Conversely, you can set :http:`request:customHttpRequestHeaders` or
    :http:`request:requestHeaders` to ``False`` to prevent their mapping from
    :attr:`Request.headers <scrapy.http.Request.headers>`.

-   :attr:`Request.body <scrapy.http.Request.body>` becomes
    :http:`request:httpRequestBody` even if :http:`request:httpResponseBody` is
    unset.

-   You can set :http:`request:httpResponseBody` to ``False`` (which unsets the
    parameter), and not set other outputs (:http:`request:browserHtml`,
    :http:`request:screenshot`, :http:`request:product`…) to ``True``. In this
    case, :attr:`Request.headers <scrapy.http.Request.headers>` is mapped as
    :http:`request:requestHeaders`.

-   You can set :http:`request:httpResponseBody` to ``True`` or use
    :ref:`automatic extraction from httpResponseBody <zapi-extract-from>`,
    and also set :http:`request:browserHtml` or :http:`request:screenshot` to
    ``True`` or use :ref:`automatic extraction from browserHtml
    <zapi-extract-from>`. In this case, :attr:`Request.headers
    <scrapy.http.Request.headers>` is mapped both as
    :http:`request:customHttpRequestHeaders` and as
    :http:`request:requestHeaders`, and :http:`request:browserHtml` is used as
    :class:`response.body <scrapy_zyte_api.responses.ZyteAPIResponse.body>`.
