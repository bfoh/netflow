import pytest

from undm.drivers.mock.lab import default_lab


@pytest.fixture(autouse=True)
def _clean_lab():
    default_lab().clear()
    default_lab().autocreate = True
    yield
    default_lab().clear()
