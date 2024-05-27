.. _response:

================
Response mapping
================

.. _response-parameters:

Parameters
==========

Zyte API response parameters are mapped into :ref:`response class
<response-classes>` attributes where possible:

-   :http:`response:url` becomes :class:`response.url
    <scrapy_zyte_api.responses.ZyteAPIResponse.url>`.

-   :http:`response:statusCode` becomes :class:`response.status
    <scrapy_zyte_api.responses.ZyteAPIResponse.status>`.

-   :http:`response:httpResponseHeaders` and
    :http:`response:experimental.responseCookies` become
    :class:`response.headers
    <scrapy_zyte_api.responses.ZyteAPIResponse.headers>`.

-   :http:`response:experimental.responseCookies` is also mapped into the
    request :reqmeta:`cookiejar <scrapy:cookiejar>`.

-   :http:`response:browserHtml` and :http:`response:httpResponseBody` are
    mapped into both
    :class:`response.text <scrapy_zyte_api.responses.ZyteAPITextResponse.text>`
    and
    :class:`response.body <scrapy_zyte_api.responses.ZyteAPIResponse.body>`.

    If none of these parameters were present, e.g. if the only requested output
    was :http:`response:screenshot`,
    :class:`response.text <scrapy_zyte_api.responses.ZyteAPITextResponse.text>`
    and
    :class:`response.body <scrapy_zyte_api.responses.ZyteAPIResponse.body>`
    would be empty.

    If a future version of Zyte API supported requesting both outputs on the
    same request, and both parameters were present,
    :http:`response:browserHtml` would be the one mapped into
    :class:`response.text <scrapy_zyte_api.responses.ZyteAPITextResponse.text>`
    and
    :class:`response.body <scrapy_zyte_api.responses.ZyteAPIResponse.body>`.

Both :ref:`response classes <response-classes>` have a
:class:`response.raw_api_response <scrapy_zyte_api.responses.ZyteAPIResponse.raw_api_response>`
attribute that contains a :class:`dict` with the complete, raw response from
Zyte API, where you can find all Zyte API response parameters, including those
that are not mapped into other response class attributes.

For example, for a request for :http:`response:httpResponseBody` and
:http:`response:httpResponseHeaders`, you would get:

.. code-block:: python

    def parse(self, response):
        print(response.url)
        # "https://quotes.toscrape.com/"
        print(response.status)
        # 200
        print(response.headers)
        # {b"Content-Type": [b"text/html"], …}
        print(response.text)
        # "<html>…</html>"
        print(response.body)
        # b"<html>…</html>"
        print(response.raw_api_response)
        # {
        #     "url": "https://quotes.toscrape.com/",
        #     "statusCode": 200,
        #     "httpResponseBody": "PGh0bWw+4oCmPC9odG1sPg==",
        #     "httpResponseHeaders": […],
        # }

For a request for :http:`response:screenshot`, on the other hand, the response
would look as follows:

.. code-block:: python

    def parse(self, response):
        print(response.url)
        # "https://quotes.toscrape.com/"
        print(response.status)
        # 200
        print(response.headers)
        # {}
        print(response.text)
        # ""
        print(response.body)
        # b""
        print(response.raw_api_response)
        # {
        #     "url": "https://quotes.toscrape.com/",
        #     "statusCode": 200,
        #     "screenshot": "iVBORw0KGgoAAAANSUh…",
        # }
        from base64 import b64decode

        print(b64decode(response.raw_api_response["screenshot"]))
        # b'\x89PNG\r\n\x1a\n\x00\x00\x00\r…'


.. _response-classes:

Classes
=======

Zyte API responses are mapped with one of the following classes:

-   :class:`~scrapy_zyte_api.responses.ZyteAPITextResponse` is used to map text
    responses, i.e. responses with :http:`response:browserHtml` or responses
    with both :http:`response:httpResponseBody` and
    :http:`response:httpResponseHeaders` with a text body (e.g. plain text,
    HTML, JSON).

-   :class:`~scrapy_zyte_api.responses.ZyteAPIResponse` is used to map any
    other response.

.. autoclass:: scrapy_zyte_api.responses.ZyteAPIResponse
    :show-inheritance:

    .. autoattribute:: url

    .. autoattribute:: status

    .. autoattribute:: headers

    .. attribute:: body
        :type: bytes

    .. autoattribute:: raw_api_response

.. autoclass:: scrapy_zyte_api.responses.ZyteAPITextResponse
    :show-inheritance:

    .. autoattribute:: url

    .. autoattribute:: status

    .. autoattribute:: headers

    .. attribute:: body
        :type: bytes

    .. attribute:: text
        :type: str

    .. autoattribute:: raw_api_response
