import pytest

from scrapy_zyte_api.utils import _user_agent, version


@pytest.mark.parametrize(
    "custom_user_agent,expected",
    (
        (
            None,
            f'scrapy-zyte-api/{version("scrapy-zyte-api")}',
        ),
        (
            "zyte-crawlers/0.0.1",
            f'scrapy-zyte-api/{version("scrapy-zyte-api")}, zyte-crawlers/0.0.1',
        ),
    ),
)
def test_user_agent(custom_user_agent, expected):
    assert _user_agent(custom_user_agent) == expected
