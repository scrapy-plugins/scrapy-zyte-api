import pytest
from packaging.version import Version
from pytest_twisted import ensureDeferred
from scrapy import __version__ as SCRAPY_VERSION

if Version(SCRAPY_VERSION) < Version("2.7"):
    pytest.skip("Skipping tests for Scrapy ≥ 2.7", allow_module_level=True)

from scrapy import Request, Spider
from scrapy.utils.misc import create_instance

from scrapy_zyte_api import ScrapyZyteAPIRequestFingerprinter

from . import get_crawler

try:
    import scrapy_poet
except ImportError:
    scrapy_poet = None


@ensureDeferred
async def test_cache():
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request = Request("https://example.com", meta={"zyte_api": True})
    fingerprint = fingerprinter.fingerprint(request)

    fingerprinter._param_parser = None  # Prevent later calls from working
    cached_fingerprint = fingerprinter.fingerprint(request)

    assert fingerprint == cached_fingerprint
    assert fingerprint == fingerprinter._cache[request]


@ensureDeferred
async def test_fallback_custom(caplog):
    class CustomFingerprinter:
        def fingerprint(self, request):
            return b"foo"

    settings = {
        "ZYTE_API_FALLBACK_REQUEST_FINGERPRINTER_CLASS": CustomFingerprinter,
    }
    crawler = await get_crawler(settings)
    with caplog.at_level("WARNING"):
        fingerprinter = create_instance(
            ScrapyZyteAPIRequestFingerprinter,
            settings=crawler.settings,
            crawler=crawler,
        )
    request = Request("https://example.com")
    assert fingerprinter.fingerprint(request) == b"foo"
    request = Request("https://example.com", meta={"zyte_api": True})
    assert fingerprinter.fingerprint(request) != b"foo"
    try:
        import scrapy_poet  # noqa: F401
    except ImportError:
        pass
    else:
        assert (
            "does not point to a subclass of scrapy_poet.ScrapyPoetRequestFingerprinter"
            in caplog.text
        )


@ensureDeferred
async def test_fallback_default():
    crawler = await get_crawler()
    fingerprinter = crawler.request_fingerprinter
    fallback_fingerprinter = (
        crawler.request_fingerprinter._fallback_request_fingerprinter
    )

    request = Request("https://example.com")
    new_fingerprint = fingerprinter.fingerprint(request)
    old_fingerprint = fallback_fingerprinter.fingerprint(request)
    assert new_fingerprint == old_fingerprint

    request = Request("https://example.com", meta={"zyte_api_automap": True})
    new_fingerprint = fingerprinter.fingerprint(request)
    assert old_fingerprint == fallback_fingerprinter.fingerprint(request)
    assert new_fingerprint != old_fingerprint


@ensureDeferred
async def test_headers():
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request1 = Request(
        "https://example.com",
        meta={
            "zyte_api": {
                "customHttpRequestHeaders": [{"name": "foo", "value": "bar"}],
                "requestHeaders": {"referer": "baz"},
            }
        },
    )
    request2 = Request("https://example.com", meta={"zyte_api": True})
    fingerprint1 = fingerprinter.fingerprint(request1)
    fingerprint2 = fingerprinter.fingerprint(request2)
    assert fingerprint1 == fingerprint2


@pytest.mark.parametrize(
    "url,params,fingerprint",
    (
        (
            "https://example.com",
            {},
            b"\xccz|-\x1c%\xc5\xa3\x813\x91\x1a\x1a<\x95\x91\xf91a\n",
        ),
        (
            "https://example.com/a",
            {},
            b"x!<\xc5\x88\x08#\x9e\xf0\x19J\xd4\x92\x88\xb9\xb9\xce}\xb5\xda",
        ),
        (
            "https://example.com?a",
            {},
            b'\x80D\xdag"E\x8d=\xc7\xd68\xe1\xfd\xfd\x91\xe8\xd2.\xe6\xe4',
        ),
        (
            "https://example.com?a=b",
            {},
            b"r\xa6\x93\xa59\xb8\xb0\x9a\x90`p\xbf8\xdbW\x0f%\x17@N",
        ),
        (
            "https://example.com?a=b&a",
            {},
            b"T\x88[O\x8f\x87\xc1\xbb\x0e\xa3\xfbg^s\xf9=\x92?\x17\xe8",
        ),
        (
            "https://example.com?a=b&a=c",
            {},
            b"\xff=\xc3\xe74`\x048\xecM\xa3\xe8&\xb9\x06\xdf\xb2\xb0\x96\x8e",
        ),
        (
            "https://example.com",
            {"httpRequestBody": "Zm9v"},
            b";*\xa9Wt\xcfcso2\x9e\xa5\xd9_\xcc~_\xf5\\\xcd",
        ),
        (
            "https://example.com",
            {"httpRequestMethod": "POST"},
            b"\xe1\xf3&2R%\x0c\x82mf\x88E\x11L\x05w+\xa6V\xcb",
        ),
        (
            "https://example.com",
            {"httpResponseBody": True},
            b"e\x1e\xd3J0ya_\xca\xc3\xa0\xbe'h\x0ff*\xa6b\xf2",
        ),
        (
            "https://example.com",
            {"httpResponseHeaders": True},
            b"\xcc^\x0e$\xa7\xe5\x97\xb8\xbf\x7f0\xa3\xec\xf5B\\\xe1h\x1c\xee",
        ),
        (
            "https://example.com",
            {"browserHtml": True},
            b"\xb2\x8e\x98\xa9\xa2\xf2\xa6\x96\x01\xf6\x1dYa\xf7\xdf\xc2\xe5>x\x11",
        ),
        (
            "https://example.com",
            {"screenshot": True},
            b"\x8a\xd1\x1fut\x99\xf1\xc4\xcc\xa8\xfd\xd9\x7f\x1fY\xf8\xdf/'\xb3",
        ),
        (
            "https://example.com",
            {"screenshotOptions": {"format": "png"}},
            b"\xe2\xba\xeb\x16\xb9\xd4\x117\x19\xac\x7f\xb3\x17\xf5\xf6\xfc\x9e\x94l\xcf",
        ),
        (
            "https://example.com",
            {"geolocation": "US"},
            b"#\xe2\\\xce\xb88\xf8\xb4\x19\xa09KL\xe4\x87\x80\x00\x00A7",
        ),
        (
            "https://example.com",
            {"javascript": False},
            b"\x1c!\x89\xfc\xadd\xb3\xbf-_\x97\xca\xc0g\xbdo\xee\xdc\xdfo",
        ),
        (
            "https://example.com",
            {"actions": [{"action": "click", "selector": ".button"}]},
            b"\x83\xfa\x04\xfal\xc6d(\xe1\x06\xf1>b\xed\xbe\xb1\xf2\xac5E",
        ),
    ),
)
@ensureDeferred
async def test_known_fingerprints(url, params, fingerprint):
    """Test that known fingerprints remain the same, i.e. make sure that we do
    not accidentally modify fingerprints with future implementation changes."""
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request = Request(url, meta={"zyte_api": params})
    actual_fingerprint = fingerprinter.fingerprint(request)
    assert actual_fingerprint == fingerprint


@ensureDeferred
async def test_metadata():
    settings = {"JOB": "1/2/3"}
    crawler = await get_crawler(settings)
    job_fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )

    crawler = await get_crawler()
    no_job_fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )

    request1 = Request("https://example.com", meta={"zyte_api": {"echoData": "foo"}})
    request2 = Request("https://example.com", meta={"zyte_api": True})

    fingerprint1 = job_fingerprinter.fingerprint(request1)
    fingerprint2 = job_fingerprinter.fingerprint(request2)
    fingerprint3 = no_job_fingerprinter.fingerprint(request1)
    fingerprint4 = no_job_fingerprinter.fingerprint(request2)

    assert fingerprint1 != fingerprint2
    assert fingerprint2 != fingerprint3
    assert fingerprint3 != fingerprint4
    assert fingerprint1 == fingerprint3
    assert fingerprint2 == fingerprint4


@pytest.mark.skipif(
    scrapy_poet is not None,
    reason=("scrapy-poet is installed, and test_deps already covers these scenarios"),
)
@ensureDeferred
async def test_only_end_parameters_matter():
    """Test that it does not matter how a request comes to use some Zyte API
    parameters, that the fingerprint is the same if the parameters actually
    sent to Zyte API are the same."""

    settings = {
        "ZYTE_API_TRANSPARENT_MODE": True,
    }
    crawler = await get_crawler(settings)
    transparent_fingerprinter = crawler.request_fingerprinter

    crawler = await get_crawler()
    default_fingerprinter = crawler.request_fingerprinter

    request = Request("https://example.com")
    fingerprint1 = transparent_fingerprinter.fingerprint(request)
    fingerprint2 = default_fingerprinter.fingerprint(request)

    raw_request = Request(
        "https://example.com",
        meta={
            "zyte_api": {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "responseCookies": True,
                },
            }
        },
    )
    fingerprint3 = transparent_fingerprinter.fingerprint(raw_request)
    fingerprint4 = default_fingerprinter.fingerprint(raw_request)

    auto_request = Request("https://example.com", meta={"zyte_api_automap": True})
    fingerprint5 = transparent_fingerprinter.fingerprint(auto_request)
    fingerprint6 = default_fingerprinter.fingerprint(auto_request)

    assert fingerprint1 != fingerprint2

    assert fingerprint3 == fingerprint4
    assert fingerprint5 == fingerprint6

    assert fingerprint1 == fingerprint3
    assert fingerprint1 == fingerprint5


@pytest.mark.parametrize(
    "url1,url2,match",
    (
        (
            "https://example.com",
            "https://example.com",
            True,
        ),
        (
            "https://example.com",
            "https://example.com/",
            True,
        ),
        (
            "https://example.com/a",
            "https://example.com/b",
            False,
        ),
        (
            "https://example.com/?1",
            "https://example.com/?2",
            False,
        ),
        (
            "https://example.com/?a=1&b=2",
            "https://example.com/?b=2&a=1",
            True,
        ),
        (
            "https://example.com",
            "https://example.com#",
            True,
        ),
        (
            "https://example.com#",
            "https://example.com#1",
            True,
        ),
        (
            "https://example.com#1",
            "https://example.com#2",
            True,
        ),
    ),
)
@ensureDeferred
async def test_url(url1, url2, match):
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request1 = Request(url1, meta={"zyte_api_automap": True})
    fingerprint1 = fingerprinter.fingerprint(request1)
    request2 = Request(url2, meta={"zyte_api_automap": True})
    fingerprint2 = fingerprinter.fingerprint(request2)
    if match:
        assert fingerprint1 == fingerprint2
    else:
        assert fingerprint1 != fingerprint2


def merge_dicts(*dicts):
    return {k: v for d in dicts for k, v in d.items()}


@pytest.mark.parametrize(
    "params,match",
    (
        # As long as browserHtml or screenshot are True, different fragments
        # make for different fingerprints, regardless of other parameters. Same
        # for extraction types if browserHtml is set in *Options.extractFrom.
        *(
            (
                merge_dicts(body, headers, unknown, browser),
                False,
            )
            for body in (
                {},
                {"httpResponseBody": False},
                {"httpResponseBody": True},
            )
            for headers in (
                {},
                {"httpResponseHeaders": False},
                {"httpResponseHeaders": True},
            )
            for unknown in (
                {},
                {"unknown": False},
                {"unknown": True},
            )
            for browser in (
                {"browserHtml": True},
                {"screenshot": True},
                {"browserHtml": True, "screenshot": False},
                {"browserHtml": False, "screenshot": True},
                {"browserHtml": True, "screenshot": True},
                {"product": True, "productOptions": {"extractFrom": "browserHtml"}},
            )
        ),
        # If neither browserHtml nor screenshot are enabled, different
        # fragments do *not* make for different fingerprints. Same for
        # extraction types if browserHtml is not set in # *Options.extractFrom.
        *(
            (
                merge_dicts(body, headers, unknown, browser),
                True,
            )
            for body in (
                {},
                {"httpResponseBody": False},
                {"httpResponseBody": True},
            )
            for headers in (
                {},
                {"httpResponseHeaders": False},
                {"httpResponseHeaders": True},
            )
            for unknown in (
                {},
                {"unknown": False},
                {"unknown": True},
            )
            for browser in (
                {},
                {"browserHtml": False},
                {"screenshot": False},
                {"browserHtml": False, "screenshot": False},
                {"product": True},
                {
                    "product": True,
                    "productOptions": {"extractFrom": "httpResponseBody"},
                },
            )
        ),
    ),
)
@ensureDeferred
async def test_url_fragments(params, match):
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request1 = Request("https://toscrape.com#1", meta={"zyte_api": params})
    fingerprint1 = fingerprinter.fingerprint(request1)
    request2 = Request("https://toscrape.com#2", meta={"zyte_api": params})
    fingerprint2 = fingerprinter.fingerprint(request2)
    if match:
        assert fingerprint1 == fingerprint2
    else:
        assert fingerprint1 != fingerprint2


@ensureDeferred
async def test_extract_types():
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request1 = Request("https://toscrape.com", meta={"zyte_api": {"product": True}})
    fingerprint1 = fingerprinter.fingerprint(request1)
    request2 = Request(
        "https://toscrape.com", meta={"zyte_api": {"productNavigation": True}}
    )
    fingerprint2 = fingerprinter.fingerprint(request2)
    assert fingerprint1 != fingerprint2


@ensureDeferred
async def test_request_body():
    crawler = await get_crawler()
    fingerprinter = create_instance(
        ScrapyZyteAPIRequestFingerprinter, settings=crawler.settings, crawler=crawler
    )
    request1 = Request(
        "https://toscrape.com", meta={"zyte_api": {"httpRequestBody": "Zm9v"}}
    )
    fingerprint1 = fingerprinter.fingerprint(request1)
    request2 = Request(
        "https://toscrape.com", meta={"zyte_api": {"httpRequestText": "foo"}}
    )
    fingerprint2 = fingerprinter.fingerprint(request2)
    assert fingerprint1 == fingerprint2


@pytest.mark.skipif(scrapy_poet is None, reason="scrapy-poet is not installed")
@ensureDeferred
async def test_deps():
    """Test that some injected dependencies do not affect fingerprinting at
    all (e.g. HttpClient) while others do (e.g. WebPage)."""
    from web_poet import HttpClient, WebPage

    request = Request("https://example.com")
    raw_request = Request(
        "https://example.com",
        meta={
            "zyte_api": {
                "httpResponseBody": True,
                "httpResponseHeaders": True,
                "experimental": {
                    "responseCookies": True,
                },
            }
        },
    )
    auto_request = Request("https://example.com", meta={"zyte_api_automap": True})

    class DepsSpider(Spider):
        name = "deps"

        def __init__(self, *args, **kwargs):
            self.client_request = Request(
                "https://example.com", callback=self.parse_client
            )
            self.client_raw_request = Request(
                "https://example.com",
                callback=self.parse_client,
                meta={
                    "zyte_api": {
                        "httpResponseBody": True,
                        "httpResponseHeaders": True,
                        "experimental": {
                            "responseCookies": True,
                        },
                    }
                },
            )
            self.client_auto_request = Request(
                "https://example.com",
                callback=self.parse_client,
                meta={"zyte_api_automap": True},
            )

            self.page_request = Request("https://example.com", callback=self.parse_page)
            self.page_raw_request = Request(
                "https://example.com",
                callback=self.parse_page,
                meta={
                    "zyte_api": {
                        "httpResponseBody": True,
                        "httpResponseHeaders": True,
                        "experimental": {
                            "responseCookies": True,
                        },
                    }
                },
            )
            self.page_auto_request = Request(
                "https://example.com",
                callback=self.parse_page,
                meta={"zyte_api_automap": True},
            )

        async def parse_client(self, response, a: HttpClient):
            pass

        async def parse_page(self, response, a: WebPage):
            pass

    default_crawler = await get_crawler(spider_cls=DepsSpider)
    default_fingerprinter = default_crawler.request_fingerprinter
    transparent_crawler = await get_crawler(
        {"ZYTE_API_TRANSPARENT_MODE": True}, spider_cls=DepsSpider
    )
    transparent_fingerprinter = transparent_crawler.request_fingerprinter

    request_default_fp = default_fingerprinter.fingerprint(request)
    request_transparent_fp = transparent_fingerprinter.fingerprint(request)
    raw_request_default_fp = default_fingerprinter.fingerprint(raw_request)
    raw_request_transparent_fp = transparent_fingerprinter.fingerprint(raw_request)
    auto_request_default_fp = default_fingerprinter.fingerprint(auto_request)
    auto_request_transparent_fp = transparent_fingerprinter.fingerprint(auto_request)

    client_request_default_fp = default_fingerprinter.fingerprint(
        default_crawler.spider.client_request
    )
    client_request_transparent_fp = transparent_fingerprinter.fingerprint(
        transparent_crawler.spider.client_request
    )
    client_raw_request_default_fp = default_fingerprinter.fingerprint(
        default_crawler.spider.client_raw_request
    )
    client_raw_request_transparent_fp = transparent_fingerprinter.fingerprint(
        transparent_crawler.spider.client_raw_request
    )
    client_auto_request_default_fp = default_fingerprinter.fingerprint(
        default_crawler.spider.client_auto_request
    )
    client_auto_request_transparent_fp = transparent_fingerprinter.fingerprint(
        transparent_crawler.spider.client_auto_request
    )

    page_request_default_fp = default_fingerprinter.fingerprint(
        default_crawler.spider.page_request
    )
    page_request_transparent_fp = transparent_fingerprinter.fingerprint(
        transparent_crawler.spider.page_request
    )
    page_raw_request_default_fp = default_fingerprinter.fingerprint(
        default_crawler.spider.page_raw_request
    )
    page_raw_request_transparent_fp = transparent_fingerprinter.fingerprint(
        transparent_crawler.spider.page_raw_request
    )
    page_auto_request_default_fp = default_fingerprinter.fingerprint(
        default_crawler.spider.page_auto_request
    )
    page_auto_request_transparent_fp = transparent_fingerprinter.fingerprint(
        transparent_crawler.spider.page_auto_request
    )

    assert request_default_fp != request_transparent_fp
    assert request_default_fp != raw_request_default_fp
    assert request_default_fp != raw_request_transparent_fp
    assert request_default_fp != auto_request_default_fp
    assert request_default_fp != auto_request_transparent_fp
    assert request_default_fp == client_request_default_fp
    assert request_default_fp != client_request_transparent_fp
    assert request_default_fp != client_raw_request_default_fp
    assert request_default_fp != client_raw_request_transparent_fp
    assert request_default_fp != client_auto_request_default_fp
    assert request_default_fp != client_auto_request_transparent_fp
    assert request_default_fp != page_request_default_fp
    assert request_default_fp != page_request_transparent_fp
    assert request_default_fp != page_raw_request_default_fp
    assert request_default_fp != page_raw_request_transparent_fp
    assert request_default_fp != page_auto_request_default_fp
    assert request_default_fp != page_auto_request_transparent_fp

    assert request_transparent_fp == raw_request_default_fp
    assert request_transparent_fp == raw_request_transparent_fp
    assert request_transparent_fp == auto_request_default_fp
    assert request_transparent_fp == auto_request_transparent_fp
    assert request_transparent_fp == client_request_transparent_fp
    assert request_transparent_fp == client_raw_request_default_fp
    assert request_transparent_fp == client_raw_request_transparent_fp
    assert request_transparent_fp == client_auto_request_default_fp
    assert request_transparent_fp == client_auto_request_transparent_fp
    assert request_transparent_fp != page_request_default_fp
    assert request_transparent_fp != page_request_transparent_fp
    assert request_transparent_fp != page_raw_request_default_fp
    assert request_transparent_fp != page_raw_request_transparent_fp
    assert request_transparent_fp != page_auto_request_default_fp
    assert request_transparent_fp != page_auto_request_transparent_fp

    assert page_request_default_fp != page_request_transparent_fp
    assert page_request_default_fp != page_raw_request_default_fp
    assert page_request_default_fp != page_raw_request_transparent_fp
    assert page_request_default_fp != page_auto_request_default_fp
    assert page_request_default_fp != page_auto_request_transparent_fp

    assert page_request_transparent_fp == page_raw_request_default_fp
    assert page_request_transparent_fp == page_raw_request_transparent_fp
    assert page_request_transparent_fp == page_auto_request_default_fp
    assert page_request_transparent_fp == page_auto_request_transparent_fp


@ensureDeferred
async def test_page_params():
    no_params_request = Request("https://example.com")
    empty_params_request = Request("https://example.com", meta={"page_params": {}})
    some_param_request = Request(
        "https://example.com", meta={"page_params": {"a": "b"}}
    )
    other_param_request = Request(
        "https://example.com", meta={"page_params": {"c": "d"}}
    )

    crawler = await get_crawler({"ZYTE_API_TRANSPARENT_MODE": True})
    fingerprinter = crawler.request_fingerprinter

    no_params_fingerprint = fingerprinter.fingerprint(no_params_request)
    empty_params_fingerprint = fingerprinter.fingerprint(empty_params_request)
    some_param_fingerprint = fingerprinter.fingerprint(some_param_request)
    other_param_fingerprint = fingerprinter.fingerprint(other_param_request)

    if scrapy_poet is None:
        assert no_params_fingerprint == empty_params_fingerprint
        assert no_params_fingerprint == some_param_fingerprint
        assert no_params_fingerprint == other_param_fingerprint
    else:
        assert no_params_fingerprint == empty_params_fingerprint
        assert no_params_fingerprint != some_param_fingerprint
        assert no_params_fingerprint != other_param_fingerprint
        assert some_param_fingerprint != other_param_fingerprint
