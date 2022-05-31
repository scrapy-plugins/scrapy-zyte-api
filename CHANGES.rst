Changes
=======


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
