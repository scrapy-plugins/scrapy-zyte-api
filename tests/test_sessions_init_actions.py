import pytest
from scrapy import Request, Spider

from scrapy_zyte_api.utils import maybe_deferred_to_future

from . import SESSION_SETTINGS, deferred_f_from_coro_f, get_crawler
from .helpers import assert_session_stats

_BASE_SETTINGS = {
    **SESSION_SETTINGS,
    "ZYTE_API_SESSION_MAX_BAD_INITS": 1,
}

_URL = "https://failing-action.example"


def _make_spider():
    class TestSpider(Spider):
        name = "test"

        async def start(self):
            for request in self.start_requests():
                yield request

        def start_requests(self):
            yield Request(_URL)

        def parse(self, response):
            pass

        def closed(self, reason):
            self.close_reason = reason

    return TestSpider


@pytest.mark.parametrize(
    ("init_params", "close_reason", "stats"),
    [
        # Single action fails (status: returned) → session invalid.
        (
            {
                "browserHtml": True,
                "actions": [
                    {"action": "click", "selector": {"type": "css", "value": "a"}}
                ],
            },
            "bad_session_inits",
            {"failing-action.example": {"init/check-failed": 1}},
        ),
        # Single action fails with onError=continue (status: continued) → session valid.
        (
            {
                "browserHtml": True,
                "actions": [
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": "a"},
                        "onError": "continue",
                    }
                ],
            },
            "finished",
            {"failing-action.example": {"init/check-passed": 1, "use/check-passed": 1}},
        ),
        # Two actions: first has onError=continue (status: continued), second has no
        # onError (status: returned) → session invalid.
        (
            {
                "browserHtml": True,
                "actions": [
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": "a"},
                        "onError": "continue",
                    },
                    {"action": "click", "selector": {"type": "css", "value": "b"}},
                ],
            },
            "bad_session_inits",
            {"failing-action.example": {"init/check-failed": 1}},
        ),
        # Two actions: both have onError=continue (status: continued for both) → valid.
        (
            {
                "browserHtml": True,
                "actions": [
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": "a"},
                        "onError": "continue",
                    },
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": "b"},
                        "onError": "continue",
                    },
                ],
            },
            "finished",
            {"failing-action.example": {"init/check-passed": 1, "use/check-passed": 1}},
        ),
        # Two actions: first has no onError (status: returned, stops), second
        # becomes notExecuted → session invalid.
        (
            {
                "browserHtml": True,
                "actions": [
                    {"action": "click", "selector": {"type": "css", "value": "a"}},
                    {
                        "action": "click",
                        "selector": {"type": "css", "value": "b"},
                        "onError": "continue",
                    },
                ],
            },
            "bad_session_inits",
            {"failing-action.example": {"init/check-failed": 1}},
        ),
        # No actions in init params → not affected.
        (
            {"browserHtml": True},
            "finished",
            {"failing-action.example": (1, 1)},
        ),
    ],
)
@deferred_f_from_coro_f
async def test_init_action_failure_invalidates(
    init_params, close_reason, stats, mockserver
):
    """When ZYTE_API_SESSION_INIT_ACTION_FAILURE_INVALIDATES_SESSION is True
    (default), a session is discarded if any of its init actions has a
    ``returned`` status in the response (i.e. failed without
    ``onError: continue``)."""
    settings = {
        **_BASE_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_PARAMS": init_params,
    }
    spider_cls = _make_spider()
    crawler = await get_crawler(settings, spider_cls=spider_cls, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.spider.close_reason == close_reason
    assert_session_stats(crawler, stats)


@deferred_f_from_coro_f
async def test_init_action_failure_invalidates_disabled(mockserver):
    """When ZYTE_API_SESSION_INIT_ACTION_FAILURE_INVALIDATES_SESSION is False,
    action failures during init are ignored."""
    settings = {
        **_BASE_SETTINGS,
        "ZYTE_API_URL": mockserver.urljoin("/"),
        "ZYTE_API_SESSION_PARAMS": {
            "browserHtml": True,
            "actions": [{"action": "click", "selector": {"type": "css", "value": "a"}}],
        },
        "ZYTE_API_SESSION_INIT_ACTION_FAILURE_INVALIDATES_SESSION": False,
    }
    spider_cls = _make_spider()
    crawler = await get_crawler(settings, spider_cls=spider_cls, setup_engine=False)
    await maybe_deferred_to_future(crawler.crawl())

    assert crawler.spider.close_reason == "finished"
    assert_session_stats(crawler, {"failing-action.example": (1, 1)})
