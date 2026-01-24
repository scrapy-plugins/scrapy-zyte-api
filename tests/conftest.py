import pytest

from .mockserver import MockServer


@pytest.fixture(scope="session")
def mockserver():
    with MockServer() as server:
        yield server


@pytest.fixture(scope="function")
def fresh_mockserver():
    with MockServer() as server:
        yield server
