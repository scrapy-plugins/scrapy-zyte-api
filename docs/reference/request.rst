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

-   :attr:`Request.headers <scrapy.http.Request.headers>` become
    :http:`request:customHttpRequestHeaders`.

-   :attr:`Request.body <scrapy.http.Request.body>` becomes
    :http:`request:httpRequestBody`.

-   If the :setting:`COOKIES_ENABLED <scrapy:COOKIES_ENABLED>` is ``True``
    (default), and :attr:`Request.meta <scrapy.http.Request.meta>` does not set
    :reqmeta:`dont_merge_cookies <scrapy:dont_merge_cookies>` to ``True``:

    -   :http:`request:responseCookies` becomes ``True``.

    -   Cookies from the :reqmeta:`cookiejar <scrapy:cookiejar>` become
        :http:`request:requestCookies`.

        All cookies from the cookie jar are set, regardless of their cookie
        domain. This is because Zyte API requests may involve requests to
        different domains (e.g. when following cross-domain redirects, or
        during browser rendering).

        See also: :ref:`ZYTE_API_MAX_COOKIES`,
        :ref:`ZYTE_API_COOKIE_MIDDLEWARE`.

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
        method="POST"
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
        "httpResponseBody": true,
        "httpResponseHeaders": true,
        "httpRequestBody": "eyJmb28iOiAiYmFyIn0=",
        "httpRequestMethod": "POST",
        "requestCookies": [
            {
                "name": "a",
                "value": "b",
                "domain": ""
            }
        ],
        "responseCookies": true,
        "url": "https://httpbin.org/anything"
    }

Header mapping
==============

When mapping headers, headers not supported by Zyte API are excluded from the
mapping by default.

Use :ref:`ZYTE_API_SKIP_HEADERS` and :ref:`ZYTE_API_BROWSER_HEADERS` to change
which headers are included or excluded from header mapping.


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
    parameter), and not set :http:`request:browserHtml` or
    :http:`request:screenshot` to ``True``. In this case,
    :attr:`Request.headers <scrapy.http.Request.headers>` is mapped as
    :http:`request:requestHeaders`.

-   You can set :http:`request:httpResponseBody` to ``True`` and also set
    :http:`request:browserHtml` or :http:`request:screenshot` to ``True``. In
    this case, :attr:`Request.headers <scrapy.http.Request.headers>` is mapped
    both as :http:`request:customHttpRequestHeaders` and as
    :http:`request:requestHeaders`, and :http:`request:browserHtml` is used as
    :class:`response.body <scrapy_zyte_api.responses.ZyteAPIResponse.body>`.
