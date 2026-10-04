import pytest
from packaging.version import Version
from scrapy import __version__ as SCRAPY_VERSION
from scrapy.utils.defer import deferred_f_from_coro_f

if Version(SCRAPY_VERSION) < Version("2.7"):
    pytest.skip("Skipping tests for Scrapy ≥ 2.7", allow_module_level=True)

from scrapy import Request

from scrapy_zyte_api import ScrapyZyteAPIRequestFingerprinter
from scrapy_zyte_api.utils import _build_from_crawler  # type: ignore[attr-defined]

from . import get_crawler


@pytest.mark.parametrize(
    ("meta", "same_fingerprint"),
    [
        # The proxy transport fingerprints differently from the HTTP API.
        ({"zyte_api": True, "zyte_api_transport": "proxy"}, False),
        # Explicitly choosing the HTTP API transport does not change the
        # fingerprint (backward compatibility).
        ({"zyte_api": True, "zyte_api_transport": "http"}, True),
        # The "auto" transport does not impact fingerprinting, both because it
        # is the default and for backward compatibility reasons. We work under
        # the assumption that, in real spiders, when the same request is
        # intended to be sent through the HTTP API and through proxy mode,
        # explicit "proxy" and "http" values are expected to be used, which do
        # generate different fingerprints.
        ({"zyte_api": True, "zyte_api_transport": "auto"}, True),
    ],
)
@deferred_f_from_coro_f
async def test_fingerprint_transport_meta(meta, same_fingerprint):
    crawler = await get_crawler()
    fingerprinter = _build_from_crawler(ScrapyZyteAPIRequestFingerprinter, crawler)
    default_request = Request("https://example.com", meta={"zyte_api": True})
    transport_request = Request("https://example.com", meta=meta)
    if same_fingerprint:
        assert fingerprinter.fingerprint(default_request) == fingerprinter.fingerprint(
            transport_request
        )
    else:
        assert fingerprinter.fingerprint(default_request) != fingerprinter.fingerprint(
            transport_request
        )


@pytest.mark.parametrize(
    ("meta", "same_fingerprint"),
    [
        # The ZYTE_API_TRANSPORT setting affects automap fingerprints.
        ({"zyte_api_automap": True}, False),
        # The ZYTE_API_TRANSPORT setting does not affect the fingerprint of
        # requests not handled by Zyte API.
        ({}, True),
    ],
)
@deferred_f_from_coro_f
async def test_fingerprint_transport_setting(meta, same_fingerprint):
    proxy_crawler = await get_crawler({"ZYTE_API_TRANSPORT": "proxy"})
    proxy_fingerprinter = _build_from_crawler(
        ScrapyZyteAPIRequestFingerprinter, proxy_crawler
    )
    http_crawler = await get_crawler()
    http_fingerprinter = _build_from_crawler(
        ScrapyZyteAPIRequestFingerprinter, http_crawler
    )
    request = Request("https://example.com", meta=meta)
    if same_fingerprint:
        assert http_fingerprinter.fingerprint(
            request
        ) == proxy_fingerprinter.fingerprint(request)
    else:
        assert http_fingerprinter.fingerprint(
            request
        ) != proxy_fingerprinter.fingerprint(request)
