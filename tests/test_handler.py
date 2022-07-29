import sys
from inspect import isclass
from typing import Any, Dict
from unittest import mock

import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request
from scrapy.exceptions import NotConfigured
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler
from zyte_api.aio.client import AsyncClient
from zyte_api.constants import API_URL

from scrapy_zyte_api.handler import ScrapyZyteAPIDownloadHandler

from . import DEFAULT_CLIENT_CONCURRENCY, SETTINGS, UNSET, make_handler, set_env
from .mockserver import MockServer


@pytest.mark.parametrize(
    "concurrency",
    (
        1,
        DEFAULT_CLIENT_CONCURRENCY,
        DEFAULT_CLIENT_CONCURRENCY + 1,
    ),
)
def test_concurrency_configuration(concurrency):
    settings = {
        **SETTINGS,
        "CONCURRENT_REQUESTS": concurrency,
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
            NotConfigured,
        ),
        (
            "",
            "",
            "",
        ),
        (
            "a",
            "",
            "a",
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


@ensureDeferred
@pytest.mark.skipif(sys.version_info < (3, 8), reason="unittest.mock.AsyncMock")
@pytest.mark.parametrize(
    "settings,meta,expected",
    [
        ({}, {}, None),
        ({"ZYTE_API_RETRY_POLICY": "a"}, {}, "a"),
        ({}, {"zyte_api_retry_policy": "b"}, "b"),
        ({"ZYTE_API_RETRY_POLICY": "a"}, {"zyte_api_retry_policy": "b"}, "b"),
    ],
)
async def test_retry_policy(
    settings: Dict[str, Any],
    meta: Dict[str, Any],
    expected: Any,
):
    meta = {"zyte_api": {"browserHtml": True}, **meta}
    async with make_handler(settings) as handler:
        req = Request("https://example.com", meta=meta)
        unmocked_client = handler._client
        handler._client = mock.AsyncMock(unmocked_client)
        handler._client.request_raw.return_value = {
            "browserHtml": "",
            "url": "",
        }
        await handler.download_request(req, None)

        # What we're interested in is the Request call in the API
        request_call = [
            c for c in handler._client.mock_calls if "request_raw(" in str(c)
        ]

        if not request_call:
            pytest.fail("The client's request_raw() method was not called.")

        actual = request_call[0].kwargs["retrying"]
        assert actual == expected


@ensureDeferred
async def test_stats():
    with MockServer() as server:
        async with make_handler({}, server.urljoin("/")) as handler:
            scrapy_stats = handler._crawler.stats
            assert scrapy_stats.get_stats() == {}

            client_stats = handler._client.agg_stats
            client_stats.n_attempts += 1

            meta = {"zyte_api": {"foo": "bar"}}
            request = Request("https://example.com", meta=meta)
            await handler.download_request(request, None)

            for suffix, value in (
                ('429', 0),
                ('errors', 0),
                ('extracted_queries', 1),
                ('fatal_errors', 0),
                ('input_queries', 1),
                ('results', 1),
                ('status_codes/200', 1),
            ):
                stat = f"scrapy-zyte-api/{suffix}"
                assert scrapy_stats.get_value(stat) == value
            for name in ('connection', 'response'):
                stat = f"scrapy-zyte-api/mean_{name}_seconds"
                value = scrapy_stats.get_value(stat)
                assert isinstance(value, float)
                assert value > 0.0
