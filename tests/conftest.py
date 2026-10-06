import pytest
from scrapy.core import engine

from .mockserver import MockServer

# Nothing but the engine heartbeat, 5 seconds by default, gets a crawl going
# after the engine starts, so every crawl in the suite would stall that long.
_HEARTBEAT_INTERVAL = 0.05
if hasattr(engine.ExecutionEngine, "_SLOT_HEARTBEAT_INTERVAL"):
    engine.ExecutionEngine._SLOT_HEARTBEAT_INTERVAL = _HEARTBEAT_INTERVAL
else:  # Scrapy < 2.14 hardcodes the interval.
    _Slot = engine.Slot  # type: ignore[attr-defined]
    _slot_init = _Slot.__init__

    def _fast_slot_init(self, *args, **kwargs):
        _slot_init(self, *args, **kwargs)
        start = self.heartbeat.start
        self.heartbeat.start = lambda interval, *a, **kw: start(
            min(interval, _HEARTBEAT_INTERVAL), *a, **kw
        )

    _Slot.__init__ = _fast_slot_init


def pytest_addoption(parser, pluginmanager):
    # When pytest-twisted is installed it provides the --reactor option (with
    # the "asyncio" and "default" choices). When it is not installed (i.e. when
    # running the test suite without a Twisted reactor) we add the option
    # ourselves, defaulting to "none".
    if pluginmanager.hasplugin("twisted"):
        return
    parser.addoption(
        "--reactor",
        default="none",
        choices=["asyncio", "default", "none"],
    )


def pytest_configure(config):
    if config.getoption("--reactor", "asyncio") == "none":
        import logging  # noqa: PLC0415

        from scrapy.utils.reactorless import (  # noqa: PLC0415
            install_reactor_import_hook,
        )

        install_reactor_import_hook()

        # The httpx-based download handler, used as a fallback when running
        # without a reactor, logs a warning about being experimental every time
        # it is instantiated. Silence it so that it does not interfere with
        # tests that inspect logging output.
        logging.getLogger("scrapy.core.downloader.handlers._base_streaming").setLevel(
            logging.ERROR
        )


@pytest.fixture(scope="session")
def mockserver():
    with MockServer() as server:
        yield server


@pytest.fixture
def fresh_mockserver():
    with MockServer() as server:
        yield server


pytest.register_assert_rewrite("tests.helpers")
