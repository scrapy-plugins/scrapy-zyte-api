from inspect import isclass

import pytest
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler
from zyte_api.aio.client import AsyncClient
from zyte_api.constants import API_URL

from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler
from . import DEFAULT_CLIENT_CONCURRENCY, set_env, SETTINGS, UNSET


@pytest.mark.parametrize(
    'concurrency',
    (
        1,
        DEFAULT_CLIENT_CONCURRENCY,
        DEFAULT_CLIENT_CONCURRENCY + 1,
    ),
)
def test_concurrency_configuration(concurrency):
    settings = {
        **SETTINGS,
        'CONCURRENT_REQUESTS': concurrency,
    }
    crawler = get_crawler(settings_dict=settings)
    handler = ScrapyZyteAPIDownloadHandler(
        settings=crawler.settings,
        crawler=crawler,
    )
    assert handler._client.n_conn == concurrency
    assert handler._session.connector.limit == concurrency


@pytest.mark.parametrize(
    "env_var,setting,expected",
    (
        (
            UNSET,
            UNSET,
            NotConfigured,
        ),
        (
            "",
            UNSET,
            "",
        ),
        (
            "a",
            UNSET,
            "a",
        ),
        (
            UNSET,
            None,
            NotConfigured,
        ),
        (
            "",
            None,
            "",
        ),
        (
            "a",
            None,
            "a",
        ),
        (
            UNSET,
            "",
            "",
        ),
        (
            "",
            "",
            "",
        ),
        (
            "a",
            "",
            "",
        ),
        (
            UNSET,
            "b",
            "b",
        ),
        (
            "",
            "b",
            "b",
        ),
        (
            "a",
            "b",
            "b",
        ),
    ),
)
def test_api_key(env_var, setting, expected):
    env = {}
    if env_var is not UNSET:
        env["ZYTE_API_KEY"] = env_var
    settings = {}
    if setting is not UNSET:
        settings["ZYTE_API_KEY"] = setting
    with set_env(**env):
        crawler = get_crawler(settings_dict=settings)

        def build_hander():
            return create_instance(
                ScrapyZyteAPIDownloadHandler,
                settings=None,
                crawler=crawler,
            )

        if isclass(expected) and issubclass(expected, Exception):
            with pytest.raises(expected):
                handler = build_hander()
        else:
            handler = build_hander()
            assert handler._client.api_key == expected


@pytest.mark.parametrize(
    "setting,expected",
    (
        (
            UNSET,
            API_URL,
        ),
        (
            None,
            API_URL,
        ),
        (
            "",
            API_URL,
        ),
        (
            "a",
            "a",
        ),
        (
            "https://api.example.com",
            "https://api.example.com",
        ),
    ),
)
def test_api_url(setting, expected):
    settings = {"ZYTE_API_KEY": "a"}
    if setting is not UNSET:
        settings["ZYTE_API_URL"] = setting
    crawler = get_crawler(settings_dict=settings)
    handler = create_instance(
        ScrapyZyteAPIDownloadHandler,
        settings=None,
        crawler=crawler,
    )
    assert handler._client.api_url == expected


def test_custom_client():
    client = AsyncClient(api_key="a", api_url="b")
    crawler = get_crawler()
    handler = ScrapyZyteAPIDownloadHandler(crawler.settings, crawler, client)
    assert handler._client == client
    assert handler._client != AsyncClient(api_key="a", api_url="b")
