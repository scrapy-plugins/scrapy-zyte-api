Changes
=======

0.16.1 (unreleased)
-------------------

* Fix ``"extractFrom": "httpResponseBody"`` causing both
  :http:`request:customHttpRequestHeaders` and :http:`request:requestHeaders`,
  which are incompatible with each other, to be set when using automatic
  request mapping.

0.16.0 (2024-02-08)
-------------------

* Removed support for Python 3.7.
* Updated requirement versions:

  * :doc:`scrapy-poet <scrapy-poet:index>` >= 0.21.0
  * :doc:`web-poet <web-poet:index>` >= 0.16.0

* Added support for :class:`web_poet.AnyResponse` dependency.
* Added support to specify the country code via :class:`typing.Annotated` and
  :class:`scrapy_zyte_api.Geolocation` dependency *(supported only on Python
  3.9+)*.
* Improved tests.

0.15.0 (2024-01-31)
-------------------

* Updated requirement versions:

  * :doc:`scrapy-poet <scrapy-poet:index>` >= 0.20.1

* Dependency injection :ref:`through scrapy-poet <scrapy-poet>` is now taken
  into account for request fingerprinting.

  Now, when scrapy-poet is installed, the default value of the
  :ref:`ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS` setting is
  :class:`scrapy_poet.ScrapyPoetRequestFingerprinter`, and a warning will be
  issued if a custom value is not a subclass of
  :class:`~scrapy_poet.ScrapyPoetRequestFingerprinter`.

* :ref:`Zyte Smart Proxy Manager special headers <spm-request-headers>` will
  now be dropped automatically when using :ref:`transparent mode <transparent>`
  or :ref:`automatic request parameters <automap>`. Where possible, they will
  be replaced with equivalent Zyte API parameters. In all cases, a warning will
  be issued.

* Covered the configuration of
  :class:`scrapy_zyte_api.ScrapyZyteAPISpiderMiddleware` in the :ref:`setup
  documentation <setup>`.

  :class:`~scrapy_zyte_api.ScrapyZyteAPISpiderMiddleware` was added in
  scrapy-zyte-api 0.13.0, and is required to automatically close spiders when
  all start requests fail because they are pointing to domains forbidden by
  Zyte API.

0.14.1 (2024-01-17)
-------------------

* The assignment of a custom download slot to requests that use Zyte API now
  also happens in the spider middleware, not only in the downloader middleware.

  This way requests get a download slot assigned before they reach the
  scheduler, making Zyte API requests work as expected with
  :class:`scrapy.pqueues.DownloaderAwarePriorityQueue`.

  .. note:: New requests created from downloader middlewares do not get their
            download slot assigned before they reach the scheduler. So, unless
            they reuse the metadata from a requests that did get a download
            slot assigned (e.g. retries, redirects), they will continue not to
            work as expected with
            :class:`~scrapy.pqueues.DownloaderAwarePriorityQueue`.

0.14.0 (2024-01-15)
-------------------

* Updated requirement versions:

  * andi >= 0.6.0
  * scrapy-poet >= 0.19.0
  * zyte-common-items >= 0.8.0

* Added support for ``zyte_common_items.JobPosting`` to the scrapy-poet provider.

0.13.0 (2023-12-13)
-------------------

* Updated requirement versions:

  * andi >= 0.5.0
  * scrapy-poet >= 0.18.0
  * web-poet >= 0.15.1
  * zyte-api >= 0.4.8

* The spider is now closed and the finish reason is set to
  ``"zyte_api_bad_key"`` or ``"zyte_api_suspended_account"`` when receiving
  "Authentication Key Not Found" or "Account Suspended" responses from Zyte
  API.

* The spider is now closed and the finish reason is set to
  ``"failed_forbidden_domain"`` when all start requests fail because they are
  pointing to domains forbidden by Zyte API.

* The spider is now closed and the finish reason is set to
  ``"plugin_conflict"`` if both scrapy-zyte-smartproxy and the transparent mode
  of scrapy-zyte-api are enabled.

* The ``extractFrom`` extraction option can now be requested by annotating the
  dependency with a ``scrapy_zyte_api.ExtractFrom`` member (e.g.
  ``product: typing.Annotated[Product, ExtractFrom.httpResponseBody]``).

* The ``Set-Cookie`` header is now removed from the response if the cookies
  were returned by Zyte API (as ``"experimental.responseCookies"``).

* The request fingerprinting was improved by refining which parts of the
  request affect the fingerprint.

* Zyte API Request IDs are now included in the error logs.

* Split README.rst into multiple documentation files and publish them on
  ReadTheDocs.

* Improve the documentation for the ``ZYTE_API_MAX_REQUESTS`` setting.

* Test and CI improvements.

0.12.2 (2023-10-19)
-------------------

* Unused ``<data type>Options`` (e.g. ``productOptions``) are now dropped
  from ``ZYTE_API_PROVIDER_PARAMS`` when sending the Zyte API request
* When logging Zyte API requests, truncation now uses
  "..." instead of Unicode ellipsis.

0.12.1 (2023-09-29)
-------------------

* The new ``_ZYTE_API_USER_AGENT`` setting allows customizing the user agent 
  string reported to Zyte API.
  
  Note that this setting is only meant for libraries and frameworks built on 
  top of scrapy-zyte-api, to report themselves to Zyte API, for client software 
  tracking and monitoring purposes. The value of this setting is *not* the 
  ``User-Agent`` header sent to upstream websites when using Zyte API.


0.12.0 (2023-09-26)
-------------------

* A new ``ZYTE_API_PROVIDER_PARAMS`` setting allows setting Zyte API
  parameters, like ``geolocation``, to be included in all Zyte API requests by
  the scrapy-poet provider.

* A new ``scrapy-zyte-api/request_args/<parameter>`` stat, counts the number of
  requests containing a given Zyte API request parameter. For example,
  ``scrapy-zyte-api/request_args/url`` counts the number of Zyte API requests
  with the URL parameter set (which should be all of them).

  Experimental is treated as a namespace, and its parameters are the ones
  counted, i.e. there is no ``scrapy-zyte-api/request_args/experimental`` stat,
  but there are stats like
  ``scrapy-zyte-api/request_args/experimental.responseCookies``.


0.11.1 (2023-08-25)
-------------------

* scrapy-zyte-api 0.11.0 accidentally increased the minimum required version of
  scrapy-poet from 0.10.0 to 0.11.0. We have reverted that change and
  implemented measures to prevent similar accidents in the future.

* Automatic parameter mapping no longer warns about dropping the
  ``Accept-Encoding`` header when the header value matches the Scrapy default.

* The README now mentions additional changes that may be necessary when
  switching Twisted reactors on existing projects.

* The README now explains how status codes, from Zyte API or from wrapped
  responses, are reflected in Scrapy stats.

0.11.0 (2023-08-07)
-------------------

* Added a ``ZYTE_API_MAX_REQUESTS`` setting to limit the number of successful
  Zyte API requests that a spider can send. Reaching the limit stops the
  spider.

* Setting ``requestCookies`` to ``[]`` in the ``zyte_api_automap`` request
  metadata field now triggers a warning.

0.10.0 (2023-07-14)
-------------------

* Added more data types to the scrapy-poet provider:

  * ``zyte_common_items.ProductList``
  * ``zyte_common_items.ProductNavigation``
  * ``zyte_common_items.Article``
  * ``zyte_common_items.ArticleList``
  * ``zyte_common_items.ArticleNavigation``

* Moved the new dependencies added in 0.9.0 and needed only for the scrapy-poet
  provider (``scrapy-poet``, ``web-poet``, ``zyte-common-items``) into the new
  optional feature ``[provider]``.

* Improved result caching in the scrapy-poet provider.

* Added a new setting, ``ZYTE_API_USE_ENV_PROXY``, which can be set to ``True``
  to access Zyte API using a proxy configured in the local environment.

* Fixed getting the Scrapy Cloud job ID.

* Improved the documentation.

* Improved the CI configuration.

0.9.0 (2023-06-13)
------------------

* New and updated requirements:

  * packaging >= 20.0
  * scrapy-poet >= 0.9.0
  * web-poet >= 0.13.0
  * zyte-common-items

* Added a scrapy-poet provider for Zyte API. Currently supported data types:

  * ``web_poet.BrowserHtml``
  * ``web_poet.BrowserResponse``
  * ``zyte_common_items.Product``

* Added a ``zyte_api_default_params`` request meta key which allows users to
  ignore the ``ZYTE_API_DEFAULT_PARAMS`` setting for individual requests.

* CI fixes.

0.8.4 (2023-05-26)
------------------

* Fixed an exception raised by the downloader middleware when cookies were
  enabled.


0.8.3 (2023-05-17)
------------------

* Made Python 3.11 support official.

* Added support for the upcoming automatic extraction feature of Zyte API.

* Included a descriptive message in the exception that triggers when the
  download handler cannot be initialized.

* Clarified that ``LOG_LEVEL`` must be ``DEBUG`` for ``ZYTE_API_LOG_REQUESTS``
  messages to be visible.


0.8.2 (2023-05-02)
------------------

* Fixed the handling of response cookies without a domain.

* CI fixes


0.8.1 (2023-04-13)
------------------

* Fixed an ``AssertionError`` when cookies are disabled.

* Added links to the README to improve navigation from GitHub.

* Added a license file (BSD-3-Clause).


0.8.0 (2023-03-28)
------------------

* Added experimental cookie support:

  * The ``experimental.responseCookies`` response parameter is now mapped to
    the response headers as ``Set-Cookie`` headers, as well as added to the
    cookiejar of the request.

  * A new boolean setting, ``ZYTE_API_EXPERIMENTAL_COOKIES_ENABLED``, can be
    set to ``True`` to enable automatic mapping of cookies from a request
    cookiejar into the ``experimental.requestCookies`` Zyte API parameter.

* ``ZyteAPITextResponse`` is now a subclass of ``HtmlResponse``, so that the
  ``open_in_browser`` function of Scrapy uses the ``.html`` extension for Zyte
  API responses.

  While not ideal, this is much better than the previous behavior, where the
  ``.html`` extension was *never* used for Zyte API responses.

* ``ScrapyZyteAPIDownloaderMiddleware`` now also supports non-string slot IDs.

0.7.1 (2023-01-25)
------------------

* It is now possible to `log the parameters of requests sent`_.

  .. _log the parameters of requests sent: https://github.com/scrapy-plugins/scrapy-zyte-api#logging-request-parameters

* Stats for HTTP and HTTPS traffic used to be kept separate, and only one of
  those sets of stats would be reported. This is fixed now.

* Fixed some code examples and references in the README.


0.7.0 (2022-12-09)
------------------

When upgrading, you should set the following in your Scrapy settings:

.. code-block:: python

  DOWNLOADER_MIDDLEWARES = {
      "scrapy_zyte_api.ScrapyZyteAPIDownloaderMiddleware": 1000,
  }
  # only applicable for Scrapy 2.7+
  REQUEST_FINGERPRINTER_CLASS = "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter"

* Fixes the issue where scrapy-zyte-api is slow when Scrapy Cloud has Autothrottle
  Addon enabled. The new ``ScrapyZyteAPIDownloaderMiddleware`` fixes this.

* It now supports Scrapy 2.7's new ``REQUEST_FINGERPRINTER_CLASS`` which ensures
  that Zyte API requests are properly fingerprinted. This addresses the issue
  where Scrapy marks POST requests as duplicate if they point to the same URL
  despite having different request bodies. As a workaround, users were marking
  their requests with ``dont_filter=True`` to prevent such dupe filtering.

  For users having ``scrapy >= 2.7``, you can simply update your Scrapy settings
  to have ``REQUEST_FINGERPRINTER_CLASS = "scrapy_zyte_api.ScrapyZyteAPIRequestFingerprinter"``.

  If your Scrapy project performs other requests aside from Zyte API, you can set
  ``ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS = "custom.RequestFingerprinter"``
  to allow custom fingerprinting. By default, the default Scrapy request
  fingerprinter is used for non-Zyte API requests.

  For users having ``scrapy < 2.7``, check the following link to see different
  ways on handling the duplicate request issue:
  https://github.com/scrapy-plugins/scrapy-zyte-api#request-fingerprinting-before-scrapy-27.

  More information about the request fingerprinting topic can be found in
  https://github.com/scrapy-plugins/scrapy-zyte-api#request-fingerprinting.

* Various improvements to docs and tests.


0.6.0 (2022-10-20)
------------------

* Add a ``ZYTE_API_TRANSPARENT_MODE`` setting, ``False`` by default, which can
  be set to ``True`` to make all requests use Zyte API by default, with request
  parameters being automatically mapped to Zyte API parameters.
* Add a Request meta key, ``zyte_api_automap``, that can be used to enable
  automatic request parameter mapping for specific requests, or to modify the
  outcome of automatic request parameter mapping for specific requests.
* Add a ``ZYTE_API_AUTOMAP_PARAMS`` setting, which is a counterpart for
  ``ZYTE_API_DEFAULT_PARAMS`` that applies to requests where automatic request
  parameter mapping is enabled.
* Add the ``ZYTE_API_SKIP_HEADERS`` and ``ZYTE_API_BROWSER_HEADERS`` settings
  to control the automatic mapping of request headers.
* Add a ``ZYTE_API_ENABLED`` setting, ``True`` by default, which can be used to
  disable this plugin.
* Document how Zyte API responses are mapped to Scrapy response subclasses.

0.5.1 (2022-09-20)
------------------

* Raise the minimum dependency of Zyte API's Python API to ``zyte-api>=0.4.0``.
  This changes all the requests to Zyte API to have have ``Accept-Encoding: br``
  and automatically decompress brotli responses.
* Rename "Zyte Data API" to simply "Zyte API" in the README.
* Lower the minimum Scrapy version from ``2.6.0`` to ``2.0.1``.

0.5.0 (2022-08-25)
------------------

* Zyte Data API error responses (after retries) are no longer ignored, and
  instead raise a ``zyte_api.aio.errors.RequestError`` exception, which allows
  user-side handling of errors and provides better feedback for debugging.
* Allowed retry policies to be specified as import path strings, which is
  required for the ``ZYTE_API_RETRY_POLICY`` setting, and allows requests with
  the ``zyte_api_retry_policy`` request.meta key to remain serializable.
* Fixed the naming of stats for some error types.
* Updated the output examples on the README.

0.4.2 (2022-08-03)
------------------

* Cleaned up Scrapy stats names: fixed an issue with ``//``, renamed
  ``scrapy-zyte-api/api_error_types/..`` to ``scrapy-zyte-api/error_types/..``,
  added ``scrapy-zyte-api/error_types/<empty>`` for cases error type is unknown;
* Added error type to the error log messages
* Testing improvements

0.4.1 (2022-08-02)
------------------

Fixed incorrect 0.4.0 release.

0.4.0 (2022-08-02)
------------------

* Requires a more recent Python client library zyte-api_ ≥ 0.3.0.

* Stats from zyte-api are now copied into Scrapy stats. The
  ``scrapy-zyte-api/request_count`` stat has been renamed to
  ``scrapy-zyte-api/processed`` accordingly.

.. _zyte-api: https://github.com/zytedata/python-zyte-api


0.3.0 (2022-07-22)
------------------

* ``CONCURRENT_REQUESTS`` Scrapy setting is properly supported; in previous
  releases max concurrency of Zyte API requests was limited to 15.
* The retry policy for Zyte API requests can be overridden, using
  either ``ZYTE_API_RETRY_POLICY`` setting or ``zyte_api_retry_policy``
  request.meta key.
* Proper response.status is set when Zyte API returns ``statusCode``
  field.
* URL of the Zyte API server can be set using ``ZYTE_API_URL``
  Scrapy setting. This feature is currently used in tests.
* The minimum required Scrapy version (2.6.0) is now enforced in setup.py.
* Test and documentation improvements.

0.2.0 (2022-05-31)
------------------

* Remove the ``Content-Decoding`` header when returning the responses.
  This prevents Scrapy from decompressing already decompressed contents done
  by Zyte Data API. Otherwise, this leads to errors inside Scrapy's
  ``HttpCompressionMiddleware``.
* Introduce ``ZyteAPIResponse`` and ``ZyteAPITextResponse`` which are subclasses
  of ``scrapy.http.Response`` and ``scrapy.http.TextResponse`` respectively.
  These new response classes hold the raw Zyte Data API response in the
  ``raw_api_response`` attribute.
* Introduce a new setting named ``ZYTE_API_DEFAULT_PARAMS``.

    * At the moment, this only applies to Zyte API enabled ``scrapy.Request``
      (which is declared by having the ``zyte_api`` parameter in the Request
      meta having valid parameters, set to ``True``, or ``{}``).

* Specify in the **README** to set ``dont_filter=True`` when using the same
  URL but with different ``zyte_api`` parameters in the Request meta. This
  is a current workaround since Scrapy will tag them as duplicate requests
  and will result in duplication filtering.
* Various documentation improvements.

0.1.0 (2022-02-03)
------------------

* Initial release
