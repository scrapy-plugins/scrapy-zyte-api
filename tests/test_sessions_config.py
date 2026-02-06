from typing import Optional

import pytest
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy import Request, Spider
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached

from scrapy_zyte_api import (
    SessionConfig,
    get_request_session_id,
    is_session_init_request,
    session_config,
)
from scrapy_zyte_api._session import session_config_registry
from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import get_crawler


@deferred_f_from_coro_f
async def test_session_config(mockserver):
    pytest.importorskip("web_poet")

    @session_config(
        [
            "postal-code-10001-a.example",
            "postal-code-10001-a-fail.example",
            "postal-code-10001-a-alternative.example",
        ]
    )
    class CustomSessionConfig(SessionConfig):
        def params(self, request: Request):
            return {
                "actions": [
                    {
                        "action": "setLocation",
                        "address": {"postalCode": "10001"},
                    }
                ]
            }

        def check(self, response: Response, request: Request) -> bool:
            domain = urlparse_cached(request).netloc
            return "fail" not in domain

        def pool(self, request: Request) -> str:
            domain = urlparse_cached(request).netloc
            if domain == "postal-code-10001-a-alternative.example":
                return "postal-code-10001-a.example"
            return domain

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = [
            "https://postal-code-10001-a.example",
            "https://postal-code-10001-a-alternative.example",
            "https://postal-code-10001-a-fail.example",
            "https://postal-code-10001-b.example",
        ]

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            for url in self.start_urls:
                yield Request(
                    url,
                    meta={
                        "zyte_api_automap": {
                            "actions": [
                                {
                                    "action": "setLocation",
                                    "address": {"postalCode": "10001"},
                                }
                            ]
                        },
                    },
                )

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/init/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/use/check-passed": 2,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a-fail.example/init/check-failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-b.example/init/failed": 1,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a-alternative.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-a-fail.example/init/failed": 1,
        "scrapy-zyte-api/sessions/pools/postal-code-10001-b.example/init/failed": 1,
    }


@deferred_f_from_coro_f
async def test_session_config_no_web_poet(mockserver):
    """If web-poet is not installed, @session_config raises a RuntimeError."""
    try:
        import web_poet  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("Test only relevant when web-poet is not installed.")

    with pytest.raises(RuntimeError):

        @session_config(["example.com"])
        class CustomSessionConfig(SessionConfig):
            pass


@deferred_f_from_coro_f
async def test_session_config_process_request_change_request(mockserver):
    pytest.importorskip("web_poet")

    @session_config("example.com")
    class CustomSessionConfig(SessionConfig):
        def __init__(self, crawler):
            super().__init__(crawler)
            self.session_data = {}

        def check(self, response: Response, request: Request) -> bool:
            if is_session_init_request(request):
                session_id = get_request_session_id(request)
                self.session_data[session_id] = {"foo": "bar"}
            return super().check(response, request)

        def process_request(self, request: Request) -> Optional[Request]:
            session_id = get_request_session_id(request)
            foo = self.session_data[session_id]["foo"]
            request.headers["foo"] = foo

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }
    request_headers = []

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            request_headers.append(response.request.headers["foo"])

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert request_headers == [b"bar"]

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_session_config_process_request_new_request(mockserver):
    pytest.importorskip("web_poet")

    @session_config("example.com")
    class CustomSessionConfig(SessionConfig):
        def __init__(self, crawler):
            super().__init__(crawler)
            self.session_data = {}

        def check(self, response: Response, request: Request) -> bool:
            if is_session_init_request(request):
                session_id = get_request_session_id(request)
                self.session_data[session_id] = {"foo": "bar"}
            return super().check(response, request)

        def process_request(self, request: Request) -> Optional[Request]:
            session_id = get_request_session_id(request)
            foo = self.session_data[session_id]["foo"]
            new_url = request.url.rstrip("/") + f"/{foo}"
            return request.replace(url=new_url)

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }
    output_urls = []

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            output_urls.append(response.url)

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert output_urls == ["https://example.com/bar"]

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/check-passed": 1,
        "scrapy-zyte-api/sessions/pools/example.com/use/check-passed": 1,
    }

    # Clean up the session config registry, and check it, otherwise we could
    # affect other tests.

    session_config_registry.__init__()  # type: ignore[misc]


@deferred_f_from_coro_f
async def test_session_config_params_error(mockserver):
    pytest.importorskip("web_poet")

    @session_config(["example.com"])
    class CustomSessionConfig(SessionConfig):
        def params(self, request: Request):
            raise Exception

    settings = {
        "RETRY_TIMES": 0,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_ENABLED": True,
        "ZYTE_API_SESSION_LOCATION": {"postalCode": "10001"},
        "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
    }

    class TestSpider(Spider):
        name = "test"
        start_urls = ["https://example.com"]

        def parse(self, response):
            pass

    crawler = await get_crawler(settings, spider_cls=TestSpider, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    session_stats = {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("scrapy-zyte-api/sessions")
    }
    assert session_stats == {
        "scrapy-zyte-api/sessions/pools/example.com/init/param-error": 1,
    }

    # Clean up the session config registry.
    session_config_registry.__init__()  # type: ignore[misc]
