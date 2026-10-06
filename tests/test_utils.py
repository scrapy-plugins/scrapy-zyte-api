import asyncio

import pytest
from twisted.internet.defer import Deferred

from scrapy_zyte_api import utils

# Which of these helpers Scrapy provides depends on its version; the rest are
# defined by scrapy_zyte_api.utils itself, and only then are their fallbacks
# worth testing.
own_defer_helpers = pytest.mark.skipif(
    utils.maybe_deferred_to_future.__module__ != utils.__name__,
    reason="Scrapy provides deferred_to_future() and maybe_deferred_to_future()",
)
own_is_asyncio_available = pytest.mark.skipif(
    utils._is_asyncio_available.__module__ != utils.__name__,  # type: ignore[attr-defined]
    reason="Scrapy provides is_asyncio_available()",
)


@own_defer_helpers
def test_set_asyncio_event_loop_without_loop(monkeypatch):
    """A new event loop is created and set as the current one when there is
    none."""
    set_loops: list = []

    def get_event_loop():
        raise RuntimeError

    monkeypatch.setattr(asyncio, "get_event_loop", get_event_loop)
    monkeypatch.setattr(asyncio, "set_event_loop", set_loops.append)
    loop = utils.set_asyncio_event_loop()
    assert set_loops == [loop]
    loop.close()


@own_defer_helpers
def test_maybe_deferred_to_future_without_asyncio(monkeypatch):
    """Without an asyncio reactor, deferreds are left as they are."""
    monkeypatch.setattr(utils, "is_asyncio_reactor_installed", lambda: False)
    deferred: Deferred = Deferred()
    assert utils.maybe_deferred_to_future(deferred) is deferred


@own_is_asyncio_available
def test_is_asyncio_available_without_reactor(monkeypatch):
    monkeypatch.setattr(utils, "_is_reactor_installed", lambda: False)
    with pytest.raises(RuntimeError, match="without an installed reactor"):
        utils._is_asyncio_available()  # type: ignore[attr-defined]


def test_schedule_coro_without_asyncio(monkeypatch):
    """Without asyncio, coroutines are scheduled as deferreds."""
    monkeypatch.setattr(utils, "_is_asyncio_available", lambda: False)
    calls = []

    async def coro():
        calls.append(True)

    utils._schedule_coro(coro())
    assert calls == [True]
