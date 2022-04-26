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
