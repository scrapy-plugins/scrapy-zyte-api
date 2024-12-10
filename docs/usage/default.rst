.. _default:

==================
Default parameters
==================

Often the same configuration needs to be used for all Zyte API requests. For
example, all requests may need to set the same :http:`request:geolocation`, or
the spider only uses :http:`request:browserHtml` requests.

The following settings allow you to define Zyte API parameters to be included
in all requests:

-   :setting:`ZYTE_API_AUTOMAP_PARAMS`, for :ref:`transparent mode <transparent>`
    and :ref:`automatic request parameters <automap>`.

-   :setting:`ZYTE_API_DEFAULT_PARAMS`, for :ref:`manual request parameters
    <manual>`.

-   :setting:`ZYTE_API_PROVIDER_PARAMS`, for :ref:`dependency injection
    <scrapy-poet>`.

For example, if you set :setting:`ZYTE_API_DEFAULT_PARAMS` to
``{"geolocation": "US"}`` and :reqmeta:`zyte_api` to ``{"browserHtml": True}``,
``{"url: "…", "geolocation": "US", "browserHtml": True}`` is sent to Zyte API.
