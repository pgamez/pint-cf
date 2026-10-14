import pint
import pytest

from pint_cf import cf_unitregistry


@pytest.fixture(scope="session")
def ureg() -> pint.UnitRegistry:
    """The default registry: UDUNITS-2 plus the CF extensions."""
    return cf_unitregistry()


@pytest.fixture(scope="session")
def strict_ureg() -> pint.UnitRegistry:
    """A registry matching plain UDUNITS-2, without the CF extensions."""
    return cf_unitregistry(cf_extensions=False)
