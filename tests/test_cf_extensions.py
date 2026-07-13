"""
Tests for CF units not supported by UDUNITS-2, added on top of the base
registry by cf_unitregistry() unless cf_extensions=False.

Covers, in order:
  - New dimensionless units (level, sigma_level, layer) and their
    DeprecationWarning.
  - practical_salinity_unit/psu.
  - decibel/bel.
  - The sverdrup/sievert "Sv" symbol reassignment, and the regression it
    could otherwise cause: `rem` (defined upstream as "cSv") must keep
    meaning centisievert, not silently become a fraction of a sverdrup.
  - cf_extensions=False: none of the above additions are present, and
    "Sv" keeps its plain UDUNITS-2 (sievert) meaning.
"""

import warnings

import pint
import pytest

from pint_cf import cf_unitregistry

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def ureg() -> pint.UnitRegistry:
    return cf_unitregistry()


@pytest.fixture(scope="module")
def strict_ureg() -> pint.UnitRegistry:
    return cf_unitregistry(cf_extensions=False)


# =============================================================================
# Conversions: (unit, target_unit, expected_magnitude)
# =============================================================================

TEST_CASES_CONVERSION = [
    ("level", "dimensionless", 1),
    ("sigma_level", "dimensionless", 1),
    ("layer", "dimensionless", 1),
    ("psu", "dimensionless", 1e-3),
    ("practical_salinity_unit", "dimensionless", 1e-3),
    ("dB", "dimensionless", 1),
    ("decibel", "dimensionless", 1),
    ("bel", "decibel", 10),
    ("Sv", "m**3/s", 1e6),
    ("sverdrup", "m**3/s", 1e6),
    # "Sv" now means sverdrup, but "sievert" the full name is unaffected.
    ("sievert", "gray", 1),
    # Regression: `rem` is defined upstream as "cSv" - reassigning "Sv" to
    # sverdrup must not silently reinterpret it as a fraction of a
    # sverdrup, it must still mean 0.01 gray (centisievert).
    ("rem", "gray", 0.01),
]


@pytest.mark.parametrize("unit, target, expected", TEST_CASES_CONVERSION)
def test_cf_extension_conversion(
    ureg: pint.UnitRegistry, unit: str, target: str, expected: float
) -> None:
    q = ureg.Quantity(1, unit)
    assert q.to(target).magnitude == pytest.approx(expected)


# =============================================================================
# Formatting: (unit, expected_cf, expected_short_cf)
# =============================================================================

TEST_CASES_FORMAT = [
    ("sverdrup", "sverdrup", "Sv"),
    ("Sv", "sverdrup", "Sv"),
    ("psu", "practical_salinity_unit", "psu"),
    ("dB", "decibel", "dB"),
]


@pytest.mark.parametrize("unit, expected_cf, expected_short_cf", TEST_CASES_FORMAT)
def test_cf_extension_format(
    ureg: pint.UnitRegistry, unit: str, expected_cf: str, expected_short_cf: str
) -> None:
    q = ureg.Quantity(1, unit)
    assert format(q, "cf") == f"1 {expected_cf}"
    assert format(q, "~cf") == f"1 {expected_short_cf}"


# =============================================================================
# Deprecated dimensionless vertical-coordinate placeholders
# =============================================================================

DEPRECATED_UNITS = ["level", "levels", "sigma_level", "sigma_levels", "layer", "layers"]

NON_DEPRECATED_UNITS = ["meter", "psu", "dB", "sverdrup"]


@pytest.mark.parametrize("unit", DEPRECATED_UNITS)
def test_deprecated_cf_unit_warns(ureg: pint.UnitRegistry, unit: str) -> None:
    with pytest.warns(DeprecationWarning, match="COARDS"):
        q = ureg.Quantity(3, unit)
    assert q.to("dimensionless").magnitude == 3


@pytest.mark.parametrize("unit", NON_DEPRECATED_UNITS)
def test_non_deprecated_unit_does_not_warn(ureg: pint.UnitRegistry, unit: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        ureg.Quantity(1, unit)


# =============================================================================
# cf_extensions=False: none of the CF additions are present
# =============================================================================

UNDEFINED_IN_STRICT_MODE = [
    "level",
    "sigma_level",
    "layer",
    "psu",
    "practical_salinity_unit",
    "decibel",
    "bel",
]


@pytest.mark.parametrize("unit", UNDEFINED_IN_STRICT_MODE)
def test_strict_mode_does_not_define_cf_extensions(
    strict_ureg: pint.UnitRegistry, unit: str
) -> None:
    with pytest.raises(pint.errors.UndefinedUnitError):
        strict_ureg.Unit(unit)


def test_strict_mode_keeps_sv_as_sievert(strict_ureg: pint.UnitRegistry) -> None:
    q = strict_ureg.Quantity(1, "Sv")
    assert q.to("gray").magnitude == pytest.approx(1)
