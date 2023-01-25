Changes
=======

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
  automated request parameter mapping for specific requests, or to modify the
  outcome of automated request parameter mapping for specific requests.
* Add a ``ZYTE_API_AUTOMAP_PARAMS`` setting, which is a counterpart for
  ``ZYTE_API_DEFAULT_PARAMS`` that applies to requests where automated request
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
