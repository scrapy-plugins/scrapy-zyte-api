import pytest

from .mockserver import MockServer


@pytest.fixture(scope="session")
def mockserver():
    with MockServer() as server:
        yield server


@pytest.fixture
def fresh_mockserver():
    with MockServer() as server:
        yield server
