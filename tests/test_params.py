import pytest

from scrapy_zyte_api._params import _may_use_browser


@pytest.mark.parametrize(
    ("params", "result"),
    (
        ({}, True),
        ({"product": True}, True),
        ({"product": True, "productOptions": {"extractFrom": "browserHtml"}}, True),
        (
            {"product": True, "productOptions": {"extractFrom": "httpResponseBody"}},
            False,
        ),
        ({"serp": True}, False),
        ({"serp": True, "serpOptions": {"extractFrom": "browserHtml"}}, True),
        ({"serp": True, "serpOptions": {"extractFrom": "httpResponseBody"}}, False),
        ({"serp": True, "productOptions": {"extractFrom": "browserHtml"}}, False),
    ),
)
def test_may_use_browser(params, result):
    assert _may_use_browser(params) == result
