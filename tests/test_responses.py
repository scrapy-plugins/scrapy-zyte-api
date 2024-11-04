from base64 import b64encode
from collections import defaultdict
from functools import partial
from typing import Any, Dict, cast

import pytest
from scrapy import Request
from scrapy.exceptions import NotSupported
from scrapy.http import Response, TextResponse
from scrapy.http.cookies import CookieJar

from scrapy_zyte_api.responses import (
    _API_RESPONSE,
    ZyteAPIResponse,
    ZyteAPITextResponse,
)
from scrapy_zyte_api.responses import _process_response as _unwrapped_process_response
from scrapy_zyte_api.utils import _RESPONSE_HAS_IP_ADDRESS, _RESPONSE_HAS_PROTOCOL

PAGE_CONTENT = "<html><body>The cake is a lie!</body></html>"
PAGE_CONTENT_2 = "<html><body>Ceci n’est pas une pipe</body></html>"
URL = "https://example.com"


INPUT_COOKIES = [
    {
        "name": "a",
        "value": "b",
        "domain": ".example.com",
        "path": "/",
        "expires": 1679893056,
        "httpOnly": True,
        "secure": True,
    },
    {
        "name": "c",
        "value": "d",
    },
]
OUTPUT_COOKIE_HEADERS = {
    b"Set-Cookie": [
        (
            b"a=b; "
            b"Domain=.example.com; "
            b"Path=/; "
            b"Expires=Mon, 27 Mar 2023 04:57:36 GMT; "
            b"HttpOnly; "
            b"Secure"
        ),
        (b"c=d"),
    ]
}

_process_response = partial(
    _unwrapped_process_response, cookie_jars=defaultdict(CookieJar)
)


def raw_api_response_browser():
    return {
        "url": URL,
        "browserHtml": PAGE_CONTENT,
        "javascript": True,
        "echoData": {"some_value": "here"},
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html"},
            {"name": "Content-Length", "value": str(len(PAGE_CONTENT))},
        ],
        "statusCode": 200,
        "experimental": {
            "responseCookies": INPUT_COOKIES,
        },
    }


def raw_api_response_body():
    return {
        "url": "https://example.com",
        "httpResponseBody": b64encode(PAGE_CONTENT.encode("utf-8")),
        "echoData": {"some_value": "here"},
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html"},
            {"name": "Content-Length", "value": str(len(PAGE_CONTENT))},
        ],
        "statusCode": 200,
        "experimental": {
            "responseCookies": INPUT_COOKIES,
        },
    }


def raw_api_response_mixed():
    return {
        "url": URL,
        "browserHtml": PAGE_CONTENT,
        "httpResponseBody": b64encode(PAGE_CONTENT_2.encode("utf-8")),
        "echoData": {"some_value": "here"},
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html"},
            {"name": "Content-Length", "value": str(len(PAGE_CONTENT_2))},
        ],
        "statusCode": 200,
        "experimental": {
            "responseCookies": INPUT_COOKIES,
        },
    }


EXPECTED_BODY = PAGE_CONTENT.encode("utf-8")


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (raw_api_response_browser, ZyteAPITextResponse),
        (raw_api_response_body, ZyteAPIResponse),
    ],
)
def test_init(api_response, cls):
    response = cls(URL, raw_api_response=api_response())
    assert response.raw_api_response == api_response()

    assert response.url == URL
    assert response.status == 200
    assert not response.headers
    assert response.body == b""
    assert not response.flags
    assert response.request is None
    assert response.certificate is None
    if _RESPONSE_HAS_IP_ADDRESS:
        assert response.ip_address is None
    if _RESPONSE_HAS_PROTOCOL:
        assert response.protocol is None


@pytest.mark.parametrize(
    "api_response,cls,content_length",
    [
        (raw_api_response_browser, ZyteAPITextResponse, 44),
        (raw_api_response_body, ZyteAPIResponse, 44),
        (raw_api_response_mixed, ZyteAPITextResponse, 49),
    ],
)
def test_text_from_api_response(api_response, cls, content_length):
    response = cls.from_api_response(api_response())
    assert response.raw_api_response == api_response()

    assert response.url == URL
    assert response.status == 200
    expected_headers = {
        b"Content-Type": [b"text/html"],
        b"Content-Length": [str(content_length).encode()],
        **OUTPUT_COOKIE_HEADERS,
    }
    assert response.headers == expected_headers
    assert response.body == EXPECTED_BODY
    assert response.flags == ["zyte-api"]
    assert response.request is None
    assert response.certificate is None
    if _RESPONSE_HAS_IP_ADDRESS:
        assert response.ip_address is None
    if _RESPONSE_HAS_PROTOCOL:
        assert response.protocol is None


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (raw_api_response_browser, ZyteAPITextResponse),
        (raw_api_response_body, ZyteAPIResponse),
    ],
)
def test_response_replace(api_response, cls):
    orig_response = cls.from_api_response(api_response())

    # It should still work the same way
    new_response = orig_response.replace(status=404)
    assert new_response.status == 404

    new_response = orig_response.replace(url="https://new-example.com")
    assert new_response.url == "https://new-example.com"

    # Ensure that the Zyte API response is intact
    assert new_response.raw_api_response == api_response()

    new_raw_api_response = {
        "url": "https://another-website.com",
        "httpResponseHeaders": {"name": "Content-Type", "value": "application/json"},
    }

    # Attempting to replace the raw_api_response value would raise an error
    with pytest.raises(ValueError):
        orig_response.replace(raw_api_response=new_raw_api_response)


def test_non_utf8_response():
    content = "<html><body>Some non-ASCII ✨ chars</body></html>"
    sample_raw_api_response = {
        "url": URL,
        "browserHtml": content,
        "httpResponseHeaders": [
            {"name": "Content-Type", "value": "text/html; charset=iso-8859-1"},
            {"name": "Content-Length", "value": str(len(content))},
        ],
    }

    # Encoding inference should not kick in under the hood for
    # ``scrapy.http.TextResponse`` since ``ZyteAPITextResponse`` using "utf-8"
    # for it. This is the default encoding for the "browserHtml" contents from
    # Zyte API. Thus, even if the Response Headers or <meta> tags indicate a
    # different encoding, it should still be treated as "utf-8".
    response = ZyteAPITextResponse.from_api_response(sample_raw_api_response)
    assert response.text == content
    assert response.encoding == "utf-8"


BODY = "<html><body>Hello<h1>World!✨</h1></body></html>"


def format_to_httpResponseBody(body, encoding="utf-8"):
    return b64encode(body.encode(encoding)).decode("utf-8")


@pytest.mark.parametrize(
    "api_response,cls",
    [
        (raw_api_response_browser, ZyteAPITextResponse),
        (raw_api_response_body, ZyteAPIResponse),
    ],
)
def test_response_headers_removal(api_response, cls):
    """Headers like 'Content-Encoding' should be removed later in the response
    instance returned to Scrapy.

    However, they should still be present inside 'raw_api_response.headers'.
    """
    additional_headers = [
        {"name": "Content-Encoding", "value": "gzip"},
        {"name": "Set-Cookie", "value": "a=b"},
        {"name": "X-Some-Other-Value", "value": "123"},
    ]
    raw_response = api_response()
    raw_response["httpResponseHeaders"] = additional_headers

    response = cls.from_api_response(raw_response)

    expected_headers = {
        b"X-Some-Other-Value": [b"123"],
        **OUTPUT_COOKIE_HEADERS,
    }
    assert response.headers == expected_headers
    assert (
        response.raw_api_response["httpResponseHeaders"]
        == raw_response["httpResponseHeaders"]
    )


INPUT_COOKIES_SIMPLE = [{"name": "c", "value": "d"}]


@pytest.mark.parametrize(
    "fields,cls,keep",
    [
        # Only keep the Set-Cookie header if experimental.responseCookies is
        # not received.
        *(
            (
                {
                    **cast(Dict[Any, Any], output_fields),
                    "httpResponseHeaders": [
                        {"name": "Content-Type", "value": "text/html"},
                        {"name": "Content-Length", "value": str(len(PAGE_CONTENT))},
                    ],
                    **cookie_fields,  # type: ignore[dict-item]
                },
                response_cls,
                keep,
            )
            for output_fields, response_cls in (
                (
                    {"httpResponseBody": b64encode(PAGE_CONTENT.encode("utf-8"))},
                    ZyteAPIResponse,
                ),
                (
                    {
                        "browserHtml": PAGE_CONTENT,
                    },
                    ZyteAPITextResponse,
                ),
            )
            for cookie_fields, keep in (
                # No response cookies, so Set-Cookie is kept.
                (
                    {},
                    True,
                ),
                # Response cookies, so Set-Cookie is not kept.
                (
                    {
                        "experimental": {
                            "responseCookies": INPUT_COOKIES_SIMPLE,
                        },
                    },
                    False,
                ),
            )
        ),
    ],
)
def test_response_cookie_header(fields, cls, keep):
    """Test the logic to keep or not the Set-Cookie header in response
    headers."""
    expected_headers = {
        **{
            header["name"].encode(): [header["value"].encode()]
            for header in fields["httpResponseHeaders"]
        },
    }
    if keep:
        expected_headers[b"Set-Cookie"] = [b"a=b"]
    elif "experimental" in fields:
        expected_headers[b"Set-Cookie"] = [b"c=d"]

    fields["url"] = "https://example.com"
    fields["statusCode"] = 200
    fields["httpResponseHeaders"].append({"name": "Set-Cookie", "value": "a=b"})

    response = cls.from_api_response(fields)

    assert response.headers == expected_headers
    assert (
        response.raw_api_response["httpResponseHeaders"]
        == fields["httpResponseHeaders"]
    )


def test__process_response_no_body():
    """The _process_response() function should handle missing 'browserHtml' or
    'httpResponseBody'.
    """
    api_response: _API_RESPONSE = {
        "url": "https://example.com",
        "product": {"name": "shoes"},
    }

    resp = _process_response(api_response, Request(cast(str, api_response["url"])))

    assert isinstance(resp, Response)
    assert resp.body == b""


def test__process_response_body_only():
    """Having the Body but with no Headers won't allow us to decode the contents
    with the proper encoding.

    Thus, we won't have access to css/xpath selectors.
    """
    encoding = "utf-8"
    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(BODY, encoding=encoding),
    }

    resp = _process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, Response)
    with pytest.raises(NotSupported):
        assert resp.css("h1 ::text")
    with pytest.raises(NotSupported):
        assert resp.xpath("//body/text()")


@pytest.mark.xfail(reason="encoding inference is not supported for now")
def test__process_response_body_only_infer_encoding():
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

    resp = _process_response(api_response, Request(api_response["url"]))

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
def test__process_response_body_and_headers(encoding, content_type):
    """Having access to the Headers allow us to properly decode the contents
    and will have access to the css/xpath selectors.
    """
    api_response = {
        "url": "https://example.com",
        "httpResponseBody": format_to_httpResponseBody(BODY, encoding=encoding),
        "httpResponseHeaders": [{"name": "Content-Type", "value": content_type}],
    }

    resp = _process_response(api_response, Request(api_response["url"]))

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
            """<html><head><meta http-equiv="Content-Type" content="text/html; charset="gb2312"></head><body>✨</body></html>""",
            "✨",
            "gb18030",
            None,
        ),
    ],
)
def test__process_response_body_and_headers_but_no_encoding(
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

    resp = _process_response(api_response, Request(api_response["url"]))

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


def test__process_response_body_and_headers_mismatch():
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

    resp = _process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)
    assert resp.css("h1 ::text").get() != "World!✨"  # mismatch
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    assert resp.encoding == "gb18030"


def test__process_response_non_text():
    """Non-textual responses like images, files, etc. won't have access to the
    css/xpath selectors.
    """
    api_response: _API_RESPONSE = {
        "url": "https://example.com/sprite.gif",
        "httpResponseBody": "",
        "httpResponseHeaders": [
            {
                "name": "Content-Type",
                "value": "image/gif",
            }
        ],
    }
    resp = _process_response(api_response, Request(cast(str, api_response["url"])))

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
def test__process_response_browserhtml(api_response):
    resp = _process_response(api_response, Request(api_response["url"]))

    assert isinstance(resp, TextResponse)
    assert resp.css("h1 ::text").get() == "World!✨"
    assert resp.xpath("//body/text()").getall() == ["Hello"]
    assert resp.encoding == "utf-8"  # Zyte API is consistent with this on browserHtml


@pytest.mark.parametrize(
    "base_kwargs_func",
    [
        raw_api_response_browser,
        raw_api_response_body,
    ],
)
@pytest.mark.parametrize(
    "kwargs,expected_status_code",
    [
        ({}, 200),
        ({"statusCode": 200}, 200),
        ({"statusCode": 404}, 404),
    ],
)
def test_status_code(base_kwargs_func, kwargs, expected_status_code):
    base_api_response = base_kwargs_func()
    del base_api_response["statusCode"]
    api_response = {**base_api_response, **kwargs}
    response = _process_response(api_response, Request(api_response["url"]))
    assert response is not None
    assert response.status == expected_status_code
