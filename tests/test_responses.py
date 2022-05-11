from base64 import b64encode

import pytest

from scrapy_zyte_api.responses import ZyteAPIResponse, ZyteAPITextResponse

PAGE_CONTENT = "<html><body>The cake is a lie!</body></html>"
URL = "https://example.com"


def api_response_browser():
    return {
        "url": URL,
        "browserHtml": PAGE_CONTENT,
        "javascript": True,
        "echoData": {"some_value": "here"},
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html"},
            {"name": "Content-Length", "value": len(PAGE_CONTENT)},
        ],
    }


def api_response_body():
    return {
        "url": "https://example.com",
        "httpResponseBody": b64encode(PAGE_CONTENT.encode("utf-8")),
        "echoData": {"some_value": "here"},
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html"},
            {"name": "Content-Length", "value": len(PAGE_CONTENT)},
        ],
    }


EXPECTED_HEADERS = {b"Content-Type": [b"text/html"], b"Content-Length": [b"44"]}
EXPECTED_BODY = PAGE_CONTENT.encode("utf-8")


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (api_response_browser, ZyteAPITextResponse),
        (api_response_body, ZyteAPIResponse),
    ],
)
def test_init(api_response, cls):
    response = cls(URL, zyte_api_response=api_response())
    assert response.zyte_api_response == api_response()

    assert response.url == URL
    assert response.status == 200
    assert not response.headers
    assert response.body == b""
    assert not response.flags
    assert response.request is None
    assert response.certificate is None
    assert response.ip_address is None
    assert response.protocol is None


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (api_response_browser, ZyteAPITextResponse),
        (api_response_body, ZyteAPIResponse),
    ],
)
def test_text_from_api_response(api_response, cls):
    response = cls.from_api_response(api_response())
    assert response.zyte_api_response == api_response()

    assert response.url == URL
    assert response.status == 200
    assert response.headers == EXPECTED_HEADERS
    assert response.body == EXPECTED_BODY
    assert response.flags == ["zyte-api"]
    assert response.request is None
    assert response.certificate is None
    assert response.ip_address is None
    assert response.protocol is None


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (api_response_browser, ZyteAPITextResponse),
        (api_response_body, ZyteAPIResponse),
    ],
)
def test_response_replace(api_response, cls):
    orig_response = cls.from_api_response(api_response())

    # It should still work the same way
    new_response = orig_response.replace(status=404)
    assert new_response.status == 404

    new_response = orig_response.replace(url="https://new-example.com")
    assert new_response.url == "https://new-example.com"


@pytest.mark.xfail
@pytest.mark.parametrize(
    "api_response,cls",
    [
        (api_response_browser, ZyteAPITextResponse),
        (api_response_body, ZyteAPIResponse),
    ],
)
def test_response_replace_zyte_api_response(api_response, cls):
    orig_response = cls.from_api_response(api_response())

    # The ``zyte_api_response`` should not be replaced.
    new_zyte_api_response = {"overridden": "value"}
    new_response = orig_response.replace(zyte_api_response=new_zyte_api_response)
    assert new_response.zyte_api_response == api_response()


def test_non_utf8_response():
    content = "<html><body>Some non-ASCII ✨ chars</body></html>"
    sample_zyte_api_response = {
        "url": URL,
        "browserHtml": content,
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html; charset=iso-8859-1"},
            {"name": "Content-Length", "value": len(content)},
        ],
    }

    # Encoding inference should not kick in under the hood for
    # ``scrapy.http.TextResponse`` since ``ZyteAPITextResponse`` using "utf-8"
    # for it. This is the default encoding for the "browserHtml" contents from
    # Zyte API. Thus, even if the Response Headers or <meta> tags indicate a
    # different encoding, it should still be treated as "utf-8".
    response = ZyteAPITextResponse.from_api_response(sample_zyte_api_response)
    assert response.text == content
    assert response.encoding == "utf-8"


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (api_response_browser, ZyteAPITextResponse),
        (api_response_body, ZyteAPIResponse),
    ],
)
def test_response_headers_removal(api_response, cls):
    """Headers like 'Content-Encoding' should be removed later in the response
    instance returned to Scrapy.

    However, it should still be present inside 'zyte_api_response.headers'.
    """
    additional_headers = [
        {"name": "Content-Encoding", "value": "gzip"},
        {"name": "X-Some-Other-Value", "value": "123"},
    ]
    raw_response = api_response()
    raw_response["httpResponseHeaders"] = additional_headers

    response = cls.from_api_response(raw_response)

    assert response.headers == {b"X-Some-Other-Value": [b"123"]}
    assert (
        response.zyte_api_response["httpResponseHeaders"]
        == raw_response["httpResponseHeaders"]
    )
