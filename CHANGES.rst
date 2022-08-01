Changes
=======

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
