import pytest


@pytest.fixture(scope="session")
def mockserver():
    from .mockserver import MockServer

    with MockServer() as server:
        yield server


@pytest.fixture(scope="function")
def fresh_mockserver():
    from .mockserver import MockServer

    with MockServer() as server:
        yield server
