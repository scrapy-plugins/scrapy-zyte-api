import pytest
from scrapy import Request
from scrapy.http import Response
from scrapy.utils.test import get_crawler

from scrapy_zyte_api import ScrapyZyteAPIHttpCachePolicy
from scrapy_zyte_api.responses import ZyteAPIResponse

URL = "https://example.com"


@pytest.mark.parametrize(
    ("actions", "should_cache"),
    [
        (None, True),
        ([], True),
        ([{"action": "waitForSelector", "status": "success"}], True),
        ([{"action": "waitForSelector", "error": "Timed out"}], False),
        (
            [
                {"action": "waitForSelector", "status": "success"},
                {"action": "click", "error": "Not found"},
            ],
            False,
        ),
    ],
)
def test_should_cache_response(actions, should_cache):
    policy = ScrapyZyteAPIHttpCachePolicy(get_crawler().settings)
    request = Request(URL)
    raw_api_response = {"url": URL}
    if actions is not None:
        raw_api_response["actions"] = actions
    response = ZyteAPIResponse.from_api_response(raw_api_response, request=request)
    assert policy.should_cache_response(response, request) is should_cache


def test_should_cache_non_zyte_api_response():
    policy = ScrapyZyteAPIHttpCachePolicy(get_crawler().settings)
    request = Request(URL)
    response = Response(URL)
    assert policy.should_cache_response(response, request) is True
