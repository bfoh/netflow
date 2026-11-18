import pytest

from undm.drivers.mock.lab import default_lab
from undm.services.provisioning import reset_simulation


@pytest.fixture(autouse=True)
def _clean_lab():
    default_lab().clear()
    default_lab().autocreate = True
    reset_simulation()
    yield
    default_lab().clear()
