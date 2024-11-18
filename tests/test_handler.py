import json
import re
from copy import deepcopy
from inspect import isclass
from typing import Any
from unittest import mock

import pytest
from pytest_twisted import ensureDeferred
from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.settings import Settings
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler
from zyte_api.aio.client import AsyncClient
from zyte_api.aio.retry import RetryFactory
from zyte_api.constants import API_URL

from scrapy_zyte_api.handler import (
    ScrapyZyteAPIDownloadHandler,
    _body_max_size_exceeded,
)
from scrapy_zyte_api.responses import ZyteAPITextResponse
from scrapy_zyte_api.utils import USER_AGENT

from . import DEFAULT_CLIENT_CONCURRENCY, SETTINGS, SETTINGS_T, UNSET
from . import get_crawler as get_crawler_zyte_api
from . import get_download_handler, make_handler, set_env
from .mockserver import MockServer


@pytest.mark.parametrize(
    "concurrency",
    (
        1,
        DEFAULT_CLIENT_CONCURRENCY,
        DEFAULT_CLIENT_CONCURRENCY + 1,
    ),
)
@ensureDeferred
async def test_concurrency_configuration(concurrency):
    settings: SETTINGS_T = {
        **SETTINGS,
        "CONCURRENT_REQUESTS": concurrency,
    }
    crawler = await get_crawler_zyte_api(settings=settings)
    handler = get_download_handler(crawler, "https")
    assert handler._client.n_conn == concurrency
    assert handler._session._session.connector.limit == concurrency


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
    settings: SETTINGS_T = {}
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
    settings: SETTINGS_T = {"ZYTE_API_KEY": "a"}
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


RETRY_POLICY_A = RetryFactory().build()
RETRY_POLICY_B = RetryFactory().build()
assert RETRY_POLICY_A != RETRY_POLICY_B


@ensureDeferred
@pytest.mark.parametrize(
    "settings,meta,expected",
    [
        ({}, {}, None),
        (
            {"ZYTE_API_RETRY_POLICY": "tests.test_handler.RETRY_POLICY_A"},
            {},
            RETRY_POLICY_A,
        ),
        ({}, {"zyte_api_retry_policy": RETRY_POLICY_B}, RETRY_POLICY_B),
        (
            {},
            {"zyte_api_retry_policy": "tests.test_handler.RETRY_POLICY_B"},
            RETRY_POLICY_B,
        ),
        (
            {"ZYTE_API_RETRY_POLICY": "tests.test_handler.RETRY_POLICY_A"},
            {"zyte_api_retry_policy": RETRY_POLICY_B},
            RETRY_POLICY_B,
        ),
        (
            {"ZYTE_API_RETRY_POLICY": "tests.test_handler.RETRY_POLICY_A"},
            {"zyte_api_retry_policy": "tests.test_handler.RETRY_POLICY_B"},
            RETRY_POLICY_B,
        ),
    ],
)
async def test_retry_policy(
    settings: SETTINGS_T,
    meta: SETTINGS_T,
    expected: Any,
):
    meta = {"zyte_api": {"browserHtml": True}, **meta}
    async with make_handler(settings) as handler:
        req = Request("https://example.com", meta=meta)
        unmocked_session = handler._session
        handler._session = mock.AsyncMock(unmocked_session)
        handler._session.get.return_value = {
            "browserHtml": "",
            "url": "",
        }
        await handler.download_request(req, None)

        # What we're interested in is the Request call in the API
        request_call = [c for c in handler._session.mock_calls if "get(" in str(c)]

        if not request_call:
            pytest.fail("The session's get() method was not called.")

        actual = request_call[0].kwargs["retrying"]
        assert actual == expected


@ensureDeferred
async def test_stats(mockserver):
    async with make_handler({}, mockserver.urljoin("/")) as handler:
        scrapy_stats = handler._stats
        assert scrapy_stats.get_stats() == {}

        meta = {
            "zyte_api": {"a": "...", "b": {"b0": "..."}, "experimental": {"c0": "..."}}
        }
        request = Request("https://example.com", meta=meta)
        await handler.download_request(request, None)

        assert set(scrapy_stats.get_stats()) == {
            f"scrapy-zyte-api/{stat}"
            for stat in (
                "429",
                "attempts",
                "error_ratio",
                "errors",
                "fatal_errors",
                "mean_connection_seconds",
                "mean_response_seconds",
                "processed",
                "request_args/a",
                "request_args/b",
                "request_args/experimental.c0",
                "request_args/url",
                "status_codes/200",
                "success_ratio",
                "success",
                "throttle_ratio",
            )
        }
        for suffix, value in (
            ("429", 0),
            ("attempts", 1),
            ("error_ratio", 0.0),
            ("errors", 0),
            ("fatal_errors", 0),
            ("processed", 1),
            ("request_args/a", 1),
            ("request_args/b", 1),
            ("request_args/experimental.c0", 1),
            ("request_args/url", 1),
            ("status_codes/200", 1),
            ("success_ratio", 1.0),
            ("success", 1),
            ("throttle_ratio", 0.0),
        ):
            stat = f"scrapy-zyte-api/{suffix}"
            assert scrapy_stats.get_value(stat) == value
        for name in ("connection", "response"):
            stat = f"scrapy-zyte-api/mean_{name}_seconds"
            value = scrapy_stats.get_value(stat)
            assert isinstance(value, float)
            assert value > 0.0


def test_single_client():
    """Make sure that the same Zyte API client is used by both download
    handlers."""
    crawler = get_crawler(settings_dict=SETTINGS)
    handler1 = ScrapyZyteAPIDownloadHandler(
        settings=crawler.settings,
        crawler=crawler,
    )
    handler2 = ScrapyZyteAPIDownloadHandler(
        settings=crawler.settings,
        crawler=crawler,
    )
    assert handler1._client is handler2._client


@ensureDeferred
@pytest.mark.parametrize(
    "settings,enabled",
    [
        ({}, False),
        ({"ZYTE_API_LOG_REQUESTS": False}, False),
        ({"ZYTE_API_LOG_REQUESTS": True}, True),
    ],
)
async def test_log_request_toggle(
    settings: SETTINGS_T,
    enabled: bool,
    mockserver,
):
    async with make_handler(settings, mockserver.urljoin("/")) as handler:
        meta = {"zyte_api": {"foo": "bar"}}
        request = Request("https://example.com", meta=meta)
        with mock.patch("scrapy_zyte_api.handler.logger") as logger:
            await handler.download_request(request, None)
        if enabled:
            logger.debug.assert_called()
        else:
            logger.debug.assert_not_called()


@ensureDeferred
@pytest.mark.parametrize(
    "settings,short_str,long_str,truncated_str",
    [
        ({}, "a" * 64, "a" * 65, "a" * 63 + "..."),
        ({"ZYTE_API_LOG_REQUESTS_TRUNCATE": 0}, "a" * 64, "a" * 65, "a" * 65),
        ({"ZYTE_API_LOG_REQUESTS_TRUNCATE": 1}, "a", "aa", "..."),
        ({"ZYTE_API_LOG_REQUESTS_TRUNCATE": 2}, "aa", "aaa", "a..."),
    ],
)
async def test_log_request_truncate(
    settings: SETTINGS_T,
    short_str: str,
    long_str: str,
    truncated_str: str,
    mockserver,
):
    settings["ZYTE_API_LOG_REQUESTS"] = True
    input_params = {
        "short": short_str,
        "long": long_str,
        "list": [
            short_str,
            long_str,
            {
                "short": short_str,
                "long": long_str,
            },
        ],
        "dict": {
            "short": short_str,
            "long": long_str,
            "list": [
                short_str,
                long_str,
            ],
        },
    }
    expected_logged_params = {
        "short": short_str,
        "long": truncated_str,
        "list": [
            short_str,
            truncated_str,
            {
                "short": short_str,
                "long": truncated_str,
            },
        ],
        "dict": {
            "short": short_str,
            "long": truncated_str,
            "list": [
                short_str,
                truncated_str,
            ],
        },
    }
    expected_api_params = deepcopy(input_params)
    async with make_handler(settings, mockserver.urljoin("/")) as handler:
        meta = {"zyte_api": input_params}
        request = Request("https://example.com", meta=meta)
        unmocked_session = handler._session
        handler._session = mock.AsyncMock(unmocked_session)
        handler._session.get.return_value = {
            "browserHtml": "",
            "url": "",
        }
        with mock.patch("scrapy_zyte_api.handler.logger") as logger:
            await handler.download_request(request, None)

        # Check that the logged params are truncated.
        logged_message = logger.debug.call_args[0][0]
        logged_params_json_match = re.search(r"\{.*", logged_message)
        assert logged_params_json_match is not None
        logged_params_json = logged_params_json_match[0]
        logged_params = json.loads(logged_params_json)
        del logged_params["url"]
        assert logged_params == expected_logged_params

        # Check that the actual params are *not* truncated.
        actual_api_params = handler._session.get.call_args[0][0]
        del actual_api_params["url"]
        assert actual_api_params == expected_api_params


@pytest.mark.parametrize("enabled", [True, False])
def test_log_request_truncate_negative(enabled):
    settings: SETTINGS_T = {
        **SETTINGS,
        "ZYTE_API_LOG_REQUESTS": enabled,
        "ZYTE_API_LOG_REQUESTS_TRUNCATE": -1,
    }
    crawler = get_crawler(settings_dict=settings)
    with pytest.raises(ValueError):
        create_instance(
            ScrapyZyteAPIDownloadHandler,
            settings=None,
            crawler=crawler,
        )


@pytest.mark.parametrize("enabled", [True, False, None])
@ensureDeferred
async def test_trust_env(enabled):
    settings: SETTINGS_T = {
        **SETTINGS,
    }
    if enabled is not None:
        settings["ZYTE_API_USE_ENV_PROXY"] = enabled
    else:
        enabled = False
    crawler = await get_crawler_zyte_api(settings=settings)
    handler = get_download_handler(crawler, "https")
    assert handler._session._session._trust_env == enabled


@pytest.mark.parametrize(
    "user_agent,expected",
    (
        (
            None,
            USER_AGENT,
        ),
        (
            "zyte-crawlers/0.0.1",
            "zyte-crawlers/0.0.1",
        ),
    ),
)
def test_user_agent_for_build_client(user_agent, expected):
    settings: Settings = Settings(
        {
            # see https://github.com/python/mypy/issues/16557#issuecomment-1831213673
            **SETTINGS,  # type: ignore[dict-item]
            "_ZYTE_API_USER_AGENT": user_agent,
        }
    )
    client = ScrapyZyteAPIDownloadHandler._build_client(settings)
    assert client.user_agent == expected


@ensureDeferred
async def test_bad_key():
    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://bad-key.example"]

        def parse(self, response):
            pass

    settings: SETTINGS_T = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "zyte_api_bad_key"


# NOTE: Under the assumption that a case of bad key will happen since the
# beginning of a crawl, we only test the start_urls scenario, and not also the
# case of follow-up responses suddenly giving such an error.


@ensureDeferred
async def test_suspended_account_start_urls():
    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://suspended-account.example"]

        def parse(self, response):
            pass

    settings: SETTINGS_T = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "zyte_api_suspended_account"


@ensureDeferred
async def test_suspended_account_callback():
    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            yield response.follow("https://suspended-account.example")

    settings: SETTINGS_T = {
        "ZYTE_API_TRANSPARENT_MODE": True,
        **SETTINGS,
    }

    with MockServer() as server:
        settings["ZYTE_API_URL"] = server.urljoin("/")
        crawler = get_crawler(TestSpider, settings_dict=settings)
        await crawler.crawl()

    assert crawler.stats
    assert crawler.stats.get_value("finish_reason") == "zyte_api_suspended_account"


@ensureDeferred
async def test_fallback_setting():
    crawler = await get_crawler_zyte_api(settings=SETTINGS)
    handler = get_download_handler(crawler, "https")
    assert isinstance(handler, ScrapyZyteAPIDownloadHandler)
    assert isinstance(handler._fallback_handler, HTTPDownloadHandler)


@pytest.mark.parametrize(
    "body_size, warnsize, maxsize, expected_result, expected_warnings",
    [
        # Warning only (exceeds warnsize but not maxsize)
        (
            1200,
            1000,
            1500,
            False,
            [
                "Actual response size 1200 larger than download warn size 1000 in request http://example.com."
            ],
        ),
        # Cancel download (exceeds both warnsize and maxsize)
        (
            1600,
            1000,
            1500,
            True,
            [
                "Actual response size 1600 larger than download warn size 1000 in request http://example.com.",
                "Dropping the response for http://example.com: actual response size 1600 larger than download max size 1500.",
            ],
        ),
        # No limits - no warnings expected
        (500, None, None, False, []),
    ],
)
def test_body_max_size_exceeded(
    body_size, warnsize, maxsize, expected_result, expected_warnings
):
    with mock.patch("scrapy_zyte_api.handler.logger") as logger:
        result = _body_max_size_exceeded(
            body_size=body_size,
            warnsize=warnsize,
            maxsize=maxsize,
            request_url="http://example.com",
        )

    assert result == expected_result

    if expected_warnings:
        for call, expected_warning in zip(
            logger.warning.call_args_list, expected_warnings
        ):
            assert call[0][0] == expected_warning
    else:
        logger.warning.assert_not_called()


@ensureDeferred
@pytest.mark.parametrize(
    "body_size, warnsize, maxsize, expect_null",
    [
        (500, None, None, False),  # No limits, should return response
        (
            1500,
            1000,
            None,
            False,
        ),  # Exceeds warnsize, should log warning but return response
        (2500, 1000, 2000, True),  # Exceeds maxsize, should return None
        (500, 1000, 2000, False),  # Within limits, should return response
        (
            1500,
            None,
            1000,
            True,
        ),  # Exceeds maxsize with no warnsize, should return None
    ],
)
async def test_download_request_limits(
    body_size, warnsize, maxsize, expect_null, mockserver
):
    settings: SETTINGS_T = {"DOWNLOAD_WARNSIZE": warnsize, "DOWNLOAD_MAXSIZE": maxsize}
    async with make_handler(settings, mockserver.urljoin("/")) as handler:
        handler._session = mock.AsyncMock()
        handler._session.get.return_value = mock.Mock(body=b"x" * body_size)

        mock_api_response = mock.Mock(body=b"x" * body_size)

        # Patch the `from_api_response` method of ZyteAPITextResponse only for the test
        with mock.patch.object(
            ZyteAPITextResponse, "from_api_response", return_value=mock_api_response
        ):
            with mock.patch(
                "scrapy_zyte_api.responses._process_response",
                return_value=mock_api_response,
            ):
                request = Request("https://example.com")
                result = await handler._download_request({}, request, None)

                if expect_null:
                    assert result is None
                else:
                    assert result is not None
