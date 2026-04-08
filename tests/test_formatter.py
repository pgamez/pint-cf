"""
Tests for the CF formatter.

The CF formatter supports two modes via format specifiers:
  - "cf"  : long form  (product="-", power="^", no ratio)
  - "~cf" : short form (product=".", power=implicit digits, ratio with "/")
"""

from typing import cast

import pint
import pytest

from pint_cf import cf_set_application_registry

# Test cases: (input_unit, expected_cf, expected_short_cf)
TEST_CASES_FORMAT = [
    # =====================================================================
    # Dimensionless
    # =====================================================================
    ("1", "1", "1"),
    # =====================================================================
    # Base units: long name ↔ symbol
    # =====================================================================
    ("meter", "meter", "m"),
    ("kilogram", "kilogram", "kg"),
    ("second", "second", "s"),
    ("kelvin", "kelvin", "K"),
    ("ampere", "ampere", "A"),
    ("mole", "mole", "mol"),
    ("candela", "candela", "cd"),
    # Short-form input produces same output
    ("m", "meter", "m"),
    ("kg", "kilogram", "kg"),
    ("s", "second", "s"),
    ("K", "kelvin", "K"),
    ("A", "ampere", "A"),
    ("mol", "mole", "mol"),
    ("cd", "candela", "cd"),
    # =====================================================================
    # Prefixed units
    # =====================================================================
    ("kilometer", "kilometer", "km"),
    ("centimeter", "centimeter", "cm"),
    ("millimeter", "millimeter", "mm"),
    ("micrometer", "micrometer", "µm"),
    ("milligram", "milligram", "mg"),
    ("millisecond", "millisecond", "ms"),
    ("microsecond", "microsecond", "µs"),
    ("hectopascal", "hectopascal", "hPa"),
    # Short-form input
    ("km", "kilometer", "km"),
    ("cm", "centimeter", "cm"),
    ("mm", "millimeter", "mm"),
    # =====================================================================
    # Derived units
    # =====================================================================
    ("newton", "newton", "N"),
    ("pascal", "pascal", "Pa"),
    ("joule", "joule", "J"),
    ("watt", "watt", "W"),
    ("hertz", "hertz", "Hz"),
    ("volt", "volt", "V"),
    ("ohm", "ohm", "Ω"),
    # Short-form input
    ("N", "newton", "N"),
    ("Pa", "pascal", "Pa"),
    ("J", "joule", "J"),
    ("W", "watt", "W"),
    ("Hz", "hertz", "Hz"),
    # =====================================================================
    # Non-SI units
    # =====================================================================
    ("degree", "arc_degree", "°"),
    ("radian", "radian", "rad"),
    ("steradian", "steradian", "sr"),
    ("liter", "liter", "L"),
    ("day", "day", "d"),
    ("hour", "hour", "h"),
    ("minute", "minute", "min"),
    # =====================================================================
    # Temperature
    # =====================================================================
    ("degree_Celsius", "degree_Celsius", "°C"),
    ("degC", "degree_Celsius", "°C"),
    # =====================================================================
    # Plural forms (normalized to singular by registry)
    # =====================================================================
    ("meters", "meter", "m"),
    ("seconds", "second", "s"),
    ("kilometers", "kilometer", "km"),
    # =====================================================================
    # Single-unit powers
    # Long: "unit^exp" | Short: "unitEXP" (positive) or "1/unitEXP" (negative)
    # =====================================================================
    ("m^2", "meter^2", "m2"),
    ("m^3", "meter^3", "m3"),
    ("s^-1", "second^-1", "1/s"),
    ("m^-2", "meter^-2", "1/m2"),
    # =====================================================================
    # Product of units (MULTIPLY)
    # Long: "-" separator, no ratio | Short: "." separator with "/" ratio
    # =====================================================================
    ("Pa s", "pascal-second", "Pa.s"),
    # =====================================================================
    # Division / compound (DIVIDE)
    # Long: negative exponents with "-" | Short: "/" ratio
    # =====================================================================
    ("m/s", "meter-second^-1", "m/s"),
    ("m/s^2", "meter-second^-2", "m/s2"),
    ("kg/m^3", "kilogram-meter^-3", "kg/m3"),
    ("W/m^2", "watt-meter^-2", "W/m2"),
    ("mol/m^3", "mole-meter^-3", "mol/m3"),
    ("K/m", "kelvin-meter^-1", "K/m"),
    ("g/kg", "gram-kilogram^-1", "g/kg"),
    ("mm/day", "millimeter-day^-1", "mm/d"),
    ("mg/kg", "milligram-kilogram^-1", "mg/kg"),
    ("1/s", "second^-1", "1/s"),
    # =====================================================================
    # Complex compounds: numerator and denominator
    # Long: all terms with "-" and "^" | Short: "." and "/" with implicit exp
    # =====================================================================
    ("kg m/s^2", "kilogram-meter-second^-2", "kg.m/s2"),
    ("kg m^2/s^2", "kilogram-meter^2-second^-2", "kg.m2/s2"),
    ("kg m^2 s^-2", "kilogram-meter^2-second^-2", "kg.m2/s2"),
    ("kg m^-1 s^-2", "kilogram-meter^-1-second^-2", "kg/m/s2"),
    ("kg/(m s^2)", "kilogram-meter^-1-second^-2", "kg/m/s2"),
    ("kg m^2 s^-2 K^-1", "kilogram-meter^2-kelvin^-1-second^-2", "kg.m2/K/s2"),
    ("mol m^-3", "mole-meter^-3", "mol/m3"),
    ("W m^-2", "watt-meter^-2", "W/m2"),
    # =====================================================================
    # Division with parenthesized denominator
    # (same physical unit, just different input syntax)
    # =====================================================================
    ("J/(kg K)", "joule-kelvin^-1-kilogram^-1", "J/K/kg"),
    ("W/(m^2 K)", "watt-kelvin^-1-meter^-2", "W/K/m2"),
]

_TEST_CASES_FORMAT_LONG = [(i[0], i[1]) for i in TEST_CASES_FORMAT]
_TEST_CASES_FORMAT_SHORT = [(i[0], i[2]) for i in TEST_CASES_FORMAT]

cf_set_application_registry()


@pytest.fixture(scope="module")
def ureg() -> pint.UnitRegistry:
    """Return the CF-compliant UnitRegistry."""
    return cast(pint.UnitRegistry, pint.get_application_registry().get())


@pytest.mark.parametrize("input_str, expected", _TEST_CASES_FORMAT_LONG)
def test_cf_format(ureg: pint.UnitRegistry, input_str: str, expected: str) -> None:
    """Long-form CF format: product='-', power='^', no ratio."""
    u = ureg.Unit(input_str)
    result = format(u, "cf")
    assert result == expected, (
        f"format(Unit('{input_str}'), 'cf') = {result!r}, expected {expected!r}"
    )


@pytest.mark.parametrize("input_str, expected", _TEST_CASES_FORMAT_SHORT)
def test_cf_short_format(
    ureg: pint.UnitRegistry, input_str: str, expected: str
) -> None:
    """Short-form CF format (~): product='.', power=implicit, ratio with '/'."""
    u = ureg.Unit(input_str)
    result = format(u, "~cf")
    assert result == expected, (
        f"format(Unit('{input_str}'), '~cf') = {result!r}, expected {expected!r}"
    )
