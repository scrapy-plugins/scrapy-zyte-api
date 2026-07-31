import pytest

from .mockserver import MockServer


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
