import pytest

from scrapy_zyte_api import utils

# Which of these helpers Scrapy provides depends on its version; the rest are
# defined by scrapy_zyte_api.utils itself, and only then are their fallbacks
# worth testing.
own_is_asyncio_available = pytest.mark.skipif(
    utils._is_asyncio_available.__module__ != utils.__name__,  # type: ignore[attr-defined]
    reason="Scrapy provides is_asyncio_available()",
)


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
