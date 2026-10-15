.. _fingerprint:

Request fingerprinting
======================

The request fingerprinter class of scrapy-zyte-api ensures that Scrapy
generates unique :ref:`request fingerprints <request-fingerprints>` for Zyte
API requests :ref:`based on some of their parameters <fingerprint-params>`.

For example, a request for :http:`request:browserHtml` and a request for
:http:`request:screenshot` with the same target URL are considered different
requests. Similarly, requests with the same target URL but different
:http:`request:actions` are also considered different requests.

Use :setting:`ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS` to define a custom
request fingerprinting for requests that do not go through Zyte API.
