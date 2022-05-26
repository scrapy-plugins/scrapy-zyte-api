from base64 import b64encode

import pytest
from scrapy import Request
from scrapy.exceptions import NotSupported
from scrapy.http import Response, TextResponse

from scrapy_zyte_api.responses import (
    ZyteAPIResponse,
    ZyteAPITextResponse,
    process_response,
)

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
    response = cls(URL, zyte_api=api_response())
    assert response.zyte_api == api_response()

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
    assert response.zyte_api == api_response()

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
def test_response_replace_zyte_api(api_response, cls):
    orig_response = cls.from_api_response(api_response())

    # The ``zyte_api`` should not be replaced.
    new_zyte_api = {"overridden": "value"}
    new_response = orig_response.replace(zyte_api=new_zyte_api)
    assert new_response.zyte_api == api_response()


def test_non_utf8_response():
    content = "<html><body>Some non-ASCII ✨ chars</body></html>"
    sample_zyte_api = {
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
    response = ZyteAPITextResponse.from_api_response(sample_zyte_api)
    assert response.text == content
    assert response.encoding == "utf-8"


BODY = "<html><body>Hello<h1>World!✨</h1></body></html>"


def format_to_httpResponseBody(body, encoding="utf-8"):
    return b64encode(body.encode(encoding)).decode("utf-8")


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

    However, it should still be present inside 'zyte_api.headers'.
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
        response.zyte_api["httpResponseHeaders"] == raw_response["httpResponseHeaders"]
    )


def test_process_response_no_body():
    """The process_response() function should handle missing 'browserHtml' or
    'httpResponseBody'.
    """
    api_response = {"url": "https://example.com", "product": {"name": "shoes"}}

    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, Response)
    assert resp.body == b""


def test_process_response_body_only():
    """Having the Body but with no Headers won't allow us to decode the contents
    with the proper encoding.

    Thus, we won't have access to css/xpath selectors.
    """
    encoding = "utf-8"
    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(BODY, encoding=encoding),
    }

    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, Response)
    with pytest.raises(NotSupported):
        assert resp.css("h1 ::text")
    with pytest.raises(NotSupported):
        assert resp.xpath("//body/text()")


@pytest.mark.xfail(reason="encoding inference is not supported for now")
def test_process_response_body_only_infer_encoding():
    """The ``scrapy.TextResponse`` class has the ability to check the encoding
    by inferring it in the HTML body.

    However, this is a bit tricky since we need to somehow ensure that the body
    we're receiving is "text/html". We can't fully determine that without the
    headers.
    """
    encoding = "gb18030"
    body = (
        "<html>"
        '<head><meta http-equiv="Content-Type" content="text/html; charset="gb2312"></head>'
        "<body>Some ✨ contents</body>"
        "</html>"
    )

    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(body, encoding=encoding),
    }

    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)
    assert resp.css("body ::text").get() == "Some ✨ contents"
    assert resp.xpath("//body/text()").getall() == ["Some ✨ contents"]


@pytest.mark.parametrize(
    "encoding,content_type",
    [
        ("utf-8", "text/html; charset=UTF-8"),
        ("gb18030", "text/html; charset=gb2312"),
    ],
)
def test_process_response_body_and_headers(encoding, content_type):
    """Having access to the Headers allow us to properly decode the contents
    and will have access to the css/xpath selectors.
    """
    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(BODY, encoding=encoding),
        "httpResponseHeaders": [{"name": "Content-Type", "value": content_type}],
    }

    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)
    assert resp.css("h1 ::text").get() == "World!✨"
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    assert resp.encoding == encoding


@pytest.mark.parametrize(
    "body,expected,actual_encoding,inferred_encoding",
    [
        ("<html><body>plain</body></html>", "plain", "cp1252", "cp1252"),
        (
            "<html><body>✨</body></html>",
            "✨",
            "utf-8",
            "utf-8",
        ),
        (
            "<html><body>✨</body></html>",
            "✨",
            "utf-16",
            "utf-16-le",
        ),
        (
            """<html><head><meta http-equiv="Content-Type" content="text/html; charset="gb2312">
            </head><body>✨</body></html>""",
            "✨",
            "gb18030",
            None,
        ),
    ],
)
def test_process_response_body_and_headers_but_no_encoding(
    body, expected, actual_encoding, inferred_encoding
):
    """Should both the body and headers are present but no 'Content-Type' encoding
    can be derived, it should infer from the body contents.
    """
    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(body, encoding=actual_encoding),
        "httpResponseHeaders": [{"name": "X-Value", "value": "some_value"}],
    }

    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)

    if inferred_encoding:
        assert resp.css("body ::text").get() == expected
        assert resp.xpath("//body/text()").get() == expected
        assert resp.encoding == inferred_encoding

    # Scrapy's ``TextResponse`` built-in inference only works on "utf-8" and
    # "Latin-1" based encodings.
    else:
        assert resp.css("body ::text").get() != expected
        assert resp.xpath("//body/text()").get() != expected
        assert resp.encoding == "ascii"


def test_process_response_body_and_headers_mismatch():
    """If the actual contents have a mismatch in terms of its encoding, we won't
    properly decode the ✨ emoji.
    """
    encoding = "utf-8"
    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(BODY, encoding=encoding),
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html; charset=gb2312"}
        ],
    }

    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)
    assert resp.css("h1 ::text").get() != "World!✨"  # mismatch
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    assert resp.encoding == "gb18030"


def test_process_response_non_text():
    """Non-textual responses like images, files, etc. won't have access to the
    css/xpath selectors.
    """
    api_response = {
        "url": "https://example.com/sprite.gif",
        "httpResponseBody": b"",
        "httpResponseHeaders": [
            {
                "name": "Content-Type",
                "value": "image/gif",
            }
        ],
    }
    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, Response)
    with pytest.raises(NotSupported):
        assert resp.css("h1 ::text")
    with pytest.raises(NotSupported):
        assert resp.xpath("//body/text()")


@pytest.mark.parametrize(
    "api_response",
    [
        {"url": "https://example.com", "browserHtml": BODY},
        {
            "url": "https://example.com",
            "browserHtml": BODY,
            "httpResponseHeaders": [
                {
                    "name": "Content-Type",
                    "value": "text/html; charset=UTF-8",
                }
            ],
        },
    ],
)
def test_process_response_browserhtml(api_response):
    resp = process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)
    assert resp.css("h1 ::text").get() == "World!✨"
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    assert resp.encoding == "utf-8"  # Zyte API is consistent with this on browserHtml
