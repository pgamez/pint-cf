"""
Tests for the CF units UDUNITS-2 doesn't define, added on top of the base
registry by cf_unitregistry() unless cf_extensions=False.

Covers, in order:
  - The additions themselves: practical_salinity_unit/psu, decibel/bel, and
    the "Sv" symbol reassigned from sievert to sverdrup - including the
    regression that could otherwise cause: `rem` (defined upstream as "cSv")
    must keep meaning centisievert, not silently become a fraction of a
    sverdrup.
  - Their CF formatting.
  - Which units warn: only the COARDS placeholders level/sigma_level/layer.
    Those are always defined, with or without cf_extensions - see
    test_cf_conformance.py (section 3.1.1).
  - cf_extensions=False: none of the additions are present, and "Sv" keeps
    its plain UDUNITS-2 (sievert) meaning.
"""

import warnings

import pint
import pytest

from pint_cf import CFDeprecatedUnitWarning

# =============================================================================
# Conversions
# =============================================================================

# (units, target, expected)
TEST_CASES_CONVERSION = [
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


@pytest.mark.parametrize("units, target, expected", TEST_CASES_CONVERSION)
def test_cf_extension_conversion(
    ureg: pint.UnitRegistry, units: str, target: str, expected: float
) -> None:
    assert ureg.Quantity(1, units).to(target).magnitude == pytest.approx(expected)


# =============================================================================
# Formatting
# =============================================================================

# (units, expected_cf, expected_short_cf)
TEST_CASES_FORMAT = [
    ("sverdrup", "sverdrup", "Sv"),
    ("Sv", "sverdrup", "Sv"),
    ("psu", "practical_salinity_unit", "psu"),
    ("dB", "decibel", "dB"),
]


@pytest.mark.parametrize("units, expected_cf, expected_short_cf", TEST_CASES_FORMAT)
def test_cf_extension_format(
    ureg: pint.UnitRegistry, units: str, expected_cf: str, expected_short_cf: str
) -> None:
    q = ureg.Quantity(1, units)
    assert format(q, "cf") == f"1 {expected_cf}"
    assert format(q, "~cf") == f"1 {expected_short_cf}"


# =============================================================================
# Only the COARDS placeholders warn
# =============================================================================

NON_DEPRECATED_UNITS = ["meter", "psu", "dB", "sverdrup"]


@pytest.mark.parametrize("units", NON_DEPRECATED_UNITS)
def test_other_units_do_not_warn(ureg: pint.UnitRegistry, units: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", CFDeprecatedUnitWarning)
        ureg.Quantity(1, units)


# =============================================================================
# cf_extensions=False
# =============================================================================

UNDEFINED_WITHOUT_CF_EXTENSIONS = ["psu", "practical_salinity_unit", "decibel", "bel"]


@pytest.mark.parametrize("units", UNDEFINED_WITHOUT_CF_EXTENSIONS)
def test_strict_registry_does_not_define_cf_extensions(
    strict_ureg: pint.UnitRegistry, units: str
) -> None:
    with pytest.raises(pint.errors.UndefinedUnitError):
        strict_ureg.Unit(units)


def test_strict_registry_keeps_sv_as_sievert(strict_ureg: pint.UnitRegistry) -> None:
    assert strict_ureg.Quantity(1, "Sv").to("gray").magnitude == pytest.approx(1)
