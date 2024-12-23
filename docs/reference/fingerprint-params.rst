.. _fingerprint-params:

=================================
Request fingerprinting parameters
=================================

The request fingerprinter class of scrapy-zyte-api generates request
fingerprints for Zyte API requests based on the following Zyte API parameters:

-   :http:`request:url` (:func:`canonicalized <w3lib.url.canonicalize_url>`)

    For URLs that include a URL fragment, like ``https://example.com#foo``, URL
    canonicalization keeps the URL fragment if :http:`request:browserHtml` or
    :http:`request:screenshot` are enabled, or if extractFrom_ is set to
    ``browserHtml``.

    .. _extractFrom: https://docs.zyte.com/zyte-api/usage/extract.html#extraction-source

-   Request attribute parameters (:http:`request:httpRequestBody`,
    :http:`request:httpRequestText`, :http:`request:httpRequestMethod`), except
    headers

    Equivalent :http:`request:httpRequestBody` and
    :http:`request:httpRequestText` values generate the same signature.

-   Output parameters (:http:`request:browserHtml`,
    :http:`request:httpResponseBody`, :http:`request:httpResponseHeaders`,
    :http:`request:responseCookies`, :http:`request:screenshot`, and
    :ref:`automatic extraction outputs <zapi-extract-fields>` like
    :http:`request:product`)

-   Rendering option parameters (:http:`request:actions`,
    :http:`request:device`, :http:`request:javascript`,
    :http:`request:screenshotOptions`, :http:`request:viewport`, and automatic
    extraction options like :http:`request:productOptions`)

-   :http:`request:geolocation`

-   :http:`request:echoData`

The following Zyte API parameters are *not* taken into account for request
fingerprinting:

-   Request header parameters (:http:`request:customHttpRequestHeaders`,
    :http:`request:requestHeaders`)

-   Request cookie parameters (:http:`request:cookieManagement`,
    :http:`request:requestCookies`)

-   Session handling parameters (:http:`request:sessionContext`,
    :http:`request:sessionContextParameters`)

-   :http:`request:jobId`

-   Experimental parameters (:http:`experimental.* <request:experimental>`)
