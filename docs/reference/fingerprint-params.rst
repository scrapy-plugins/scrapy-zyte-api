.. _fingerprint-params:

=================================
Request fingerprinting parameters
=================================

The request fingerprinter class of scrapy-zyte-api generates request
fingerprints for Zyte API requests based on the following Zyte API parameters:

-   :http:`request:url` (:func:`canonicalized <w3lib.url.canonicalize_url>`)

    For URLs that include a URL fragment, like ``https://example.com#foo``, URL
    canonicalization keeps the URL fragment if :http:`request:browserHtml` or
    :http:`request:screenshot` are enabled.

-   Request attribute parameters (:http:`request:httpRequestBody`,
    :http:`request:httpRequestMethod`)

-   Output parameters (:http:`request:browserHtml`,
    :http:`request:httpResponseBody`, :http:`request:httpResponseHeaders`,
    :http:`request:screenshot`)

-   Rendering option parameters (:http:`request:actions`,
    :http:`request:javascript`, :http:`request:screenshotOptions`)

-   :http:`request:geolocation`

The following Zyte API parameters are *not* taken into account for request
fingerprinting:

-   Request header parameters (:http:`request:customHttpRequestHeaders`,
    :http:`request:requestHeaders`)

-   Metadata parameters (:http:`request:echoData`, :http:`request:jobId`)

-   Experimental parameters (:http:`request:experimental`)
