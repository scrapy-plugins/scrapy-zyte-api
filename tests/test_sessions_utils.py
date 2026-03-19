import pytest
from scrapy import Request

from scrapy_zyte_api import is_session_init_request
from scrapy_zyte_api._session import SESSION_INIT_META_KEY


@pytest.mark.parametrize(
    ("meta", "expected"),
    (
        ({}, False),
        ({SESSION_INIT_META_KEY: False}, False),
        ({SESSION_INIT_META_KEY: True}, True),
    ),
)
def test_is_session_init_request(meta, expected):
    actual = is_session_init_request(Request("https://example.com", meta=meta))
    assert expected == actual
