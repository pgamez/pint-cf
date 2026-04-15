import pint
import pytest

from pint_cf import cf_unitregistry


@pytest.fixture
def ureg() -> pint.UnitRegistry:
    """Return the CF-compliant UnitRegistry."""
    return cf_unitregistry()
