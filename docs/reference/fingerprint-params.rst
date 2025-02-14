.. _fingerprint-params:

=================================
Request fingerprinting parameters
=================================

The request fingerprinter class of scrapy-zyte-api generates request
fingerprints for Zyte API requests based on the following Zyte API parameters:

-   :http:`request:url` (:func:`canonicalized <w3lib.url.canonicalize_url>`).

    For URLs that include a URL fragment, like ``https://example.com#foo``, URL
    canonicalization keeps the URL fragment if the request *may* be a browser
    request.

-   Request attribute parameters (:http:`request:httpRequestBody`,
    :http:`request:httpRequestText`, :http:`request:httpRequestMethod`), except
    headers.

    Equivalent :http:`request:httpRequestBody` and
    :http:`request:httpRequestText` values generate the same signature.

-   Output parameters (:http:`request:browserHtml`,
    :http:`request:httpResponseBody`, :http:`request:httpResponseHeaders`,
    :http:`request:responseCookies`, :http:`request:screenshot`,
    :ref:`automatic extraction outputs <zapi-extract-fields>` like
    :http:`request:product`, and :http:`request:customAttributes`).

    Same for :http:`request:networkCapture`, although it is not a proper output
    parameter (it needs to be combined with another browser rendering parameter
    to work).

-   Rendering option parameters (:http:`request:actions`,
    :http:`request:device`, :http:`request:javascript`,
    :http:`request:screenshotOptions`, :http:`request:viewport`, and automatic
    extraction options like :http:`request:productOptions` or
    :http:`request:customAttributesOptions`).

-   :http:`request:geolocation`.

-   :http:`request:sessionContext`.

    When using the :ref:`session management API <session>`, :ref:`session pool
    IDs <session-pools>` are treated the same as
    :http:`request:sessionContext`.

-   :http:`request:followRedirect`.

-   :http:`request:echoData`.

-   :http:`request:tags`.

The following Zyte API parameters are *not* taken into account for request
fingerprinting by default:

-   Request header parameters (:http:`request:customHttpRequestHeaders`,
    :http:`request:requestHeaders`).

-   Request cookie parameters (:http:`request:cookieManagement`,
    :http:`request:requestCookies`).

-   :http:`request:sessionContextParameters`.

    When using the :ref:`session management API <session>`, :ref:`session
    initialization parameters <session-init>` are treated the same as
    :http:`request:sessionContextParameters`.

-   :http:`request:session.id`.

-   :http:`request:ipType`.

-   :http:`request:jobId`.

-   Experimental parameters (:http:`experimental.* <request:experimental>`).
