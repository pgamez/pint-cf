"""
Conformance with the units-related requirements of the CF conventions.

Organized by section of CF 1.13 (17 December 2025), the latest released
version; each block quotes the sentence it checks:
https://cfconventions.org/Data/cf-conventions/cf-conventions-1.13/cf-conventions.html

  3.1    Units
  3.1.1  Dimensionless units
  3.1.2  Temperature units (units_metadata)
  3.1.3  Scale factors and offsets
  3.3    Standard Name (canonical units)
  4.1    Latitude coordinate
  4.2    Longitude coordinate
  4.3    Vertical coordinate (and 4.3.2, dimensionless vertical coordinate)
  4.4.2  Time coordinate units
  7.5.3  Temporal anomalies
  App. E Cell methods that change units

Numbers matter: a scientist expects the conversions CF describes, so these
tests check converted values, not just which pint unit a string resolves
to. Wherever pint-cf can't honor CF, it must fail loudly rather than return
a wrong number.

Known gaps are marked `xfail(strict=True)` with the CODE_REVIEW.md finding
that tracks them: they document the gap, and fail (as XPASS) once it's
fixed, so the marker can't outlive the bug.
"""

import math
from pathlib import Path

import numpy as np
import pint
import pytest
from lark.exceptions import LarkError

from pint_cf import CFContext, CFDeprecatedUnitWarning, cf_attributes_for

ON_SCALE = "temperature: on_scale"
DIFFERENCE = "temperature: difference"
UNKNOWN = "temperature: unknown"

DEGREE_IN_RADIANS = math.pi / 180

# What rejecting a unit string looks like today. LarkError is a parser
# internal leaking into the public API - CODE_REVIEW 8.
REJECTED = (ValueError, NotImplementedError, LarkError)


def _read(
    ureg: pint.UnitRegistry, value: object, units: str, units_metadata: str | None
) -> pint.Quantity:
    """Read a variable the way a CF-aware reader would."""
    with CFContext(units_metadata=units_metadata):
        return ureg.Quantity(value, units)


def _xfail(finding: str, reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=f"CODE_REVIEW {finding}: {reason}")


# =============================================================================
# 3.1 Units
# =============================================================================

# "If multiplication by a dimensionless constant [...] [is] the only
# operation required [...] we describe the two units as physically
# equivalent." (units, target, factor)
TEST_CASES_PHYSICALLY_EQUIVALENT = [
    ("km", "m", 1000),
    ("hPa", "Pa", 100),
    ("mm day-1", "m s-1", 1e-3 / 86400),
    ("g kg-1", "1", 1e-3),
    ("degrees", "rad", DEGREE_IN_RADIANS),
]

# "Note that case is significant in the units strings."
TEST_CASES_CASE_SIGNIFICANT = [
    ("Pa", "PA"),  # pascal, petaampere
    ("s", "S"),  # second, siemens
    ("t", "T"),  # tonne, tesla
    ("mm", "Mm"),  # millimetre, megametre
]


@pytest.mark.parametrize("units, target, factor", TEST_CASES_PHYSICALLY_EQUIVALENT)
def test_physically_equivalent_units_convert_by_a_factor(
    ureg: pint.UnitRegistry, units: str, target: str, factor: float
) -> None:
    assert ureg.Quantity(1, units).to(target).magnitude == pytest.approx(factor)


@pytest.mark.parametrize("units, other_case", TEST_CASES_CASE_SIGNIFICANT)
def test_case_is_significant(
    ureg: pint.UnitRegistry, units: str, other_case: str
) -> None:
    assert ureg.Unit(units) != ureg.Unit(other_case)


# =============================================================================
# 3.1.1 Dimensionless units
# =============================================================================

# "The UDUNITS package defines a few dimensionless units, such as percent,
# ppm (parts per million, 1e-6), and ppb (parts per billion, 1e-9)." - and
# "the units for a dimensionless quantity may be given as a ratio of
# dimensional units, for instance mg kg-1 for a mass ratio of 1e-6, or
# microlitre litre-1 for a volume ratio of 1e-6". ppmv/ppbv are allowed when
# the variable has no standard_name. (units, value)
TEST_CASES_DIMENSIONLESS = [
    ("1", 1),
    ("percent", 1e-2),
    ("%", 1e-2),
    ("ppm", 1e-6),
    ("ppb", 1e-9),
    ("mg kg-1", 1e-6),
    ("microlitre litre-1", 1e-6),
    ("ppmv", 1e-6),
    ("ppbv", 1e-9),
]

# "the text strings level, layer, and sigma_level are allowed in the units
# attribute, in order to indicate dimensionless vertical coordinates [...]
# deprecated by this standard" (also 4.3.2).
COARDS_VERTICAL_UNITS = ["level", "layer", "sigma_level"]


def test_no_units_is_dimensionless(ureg: pint.UnitRegistry) -> None:
    """ "A variable with no units attribute is assumed to be dimensionless.\""""
    assert ureg.Quantity(1, "").dimensionless


@pytest.mark.parametrize("units, value", TEST_CASES_DIMENSIONLESS)
def test_dimensionless_units(ureg: pint.UnitRegistry, units: str, value: float) -> None:
    q = ureg.Quantity(1, units)
    assert q.dimensionless
    assert q.to("1").magnitude == pytest.approx(value)


@pytest.mark.parametrize("units", COARDS_VERTICAL_UNITS)
@pytest.mark.parametrize("registry", ["ureg", "strict_ureg"])
def test_coards_vertical_units_are_allowed_but_deprecated(
    request: pytest.FixtureRequest, registry: str, units: str
) -> None:
    """Allowed regardless of cf_extensions, since CF allows them outright."""
    with pytest.warns(CFDeprecatedUnitWarning):
        q = request.getfixturevalue(registry).Quantity(3, units)
    assert q.dimensionless
    assert q.to("1").magnitude == 3


# =============================================================================
# 3.1.2 Temperature units
# =============================================================================

# "This attribute must have one of the following three values"


@pytest.mark.parametrize("units_metadata", [ON_SCALE, DIFFERENCE, UNKNOWN])
def test_the_three_units_metadata_values_are_accepted(units_metadata: str) -> None:
    with CFContext(units_metadata=units_metadata):
        pass


@pytest.mark.parametrize(
    "units_metadata", ["temperature: absolute", "temperature: delta", "on_scale"]
)
def test_any_other_units_metadata_value_is_rejected(units_metadata: str) -> None:
    with pytest.raises(ValueError), CFContext(units_metadata=units_metadata):
        pass


# On-scale: "the data may require the addition of an offset as well as
# multiplication by a scale factor" - "0 degC is not the same temperature as
# 0 degF (= -17.8 degC)". (value, units, target, expected)
TEST_CASES_ON_SCALE_CONVERSIONS = [
    (0, "degC", "degF", 32),
    (0, "degF", "degC", -17.7778),
    (15, "degC", "K", 288.15),
    (273.15, "K", "degC", 0),
    (273.15, "K", "degF", 32),
    (491.67, "degR", "degC", 0),
]

# Difference: "to convert the units of a temperature difference requires
# only multiplication by a scale factor, without the addition of an offset".
# (value, units, target, expected)
TEST_CASES_DIFFERENCE_CONVERSIONS = [
    (1, "degC", "degF", 1.8),
    (1, "degC", "K", 1),
    (1, "degF", "degC", 1 / 1.8),
    (1, "K", "degF", 1.8),
    (1, "K", "degC", 1),
    (1, "degR", "degC", 1 / 1.8),
]

# After leaving the block, the target carries no units_metadata - CF reads
# that as "unknown", with no guaranteed conversion. A Celsius/Fahrenheit
# difference still keeps its meaning in pint (delta_), so it's never given
# an offset. Kelvin/Rankine don't: pint stores on-scale and difference as
# the same unit, so for those CFContext documents converting inside the
# block.
TEST_CASES_DIFFERENCE_CONVERSIONS_AFTER_THE_BLOCK = [
    case for case in TEST_CASES_DIFFERENCE_CONVERSIONS if case[1] in ("degC", "degF")
]

# "This ambiguity also affects units of temperature raised to some power
# e.g. K^2 or multiplied by other units e.g. W m-2 K-1, degF/foot or degC m
# s-1" - with "difference" (or "unknown"/absent, by the UDUNITS rule CF quotes
# as guidance) they convert by scale factor only. Trends of a temperature
# difference (anomaly trends) are such units too; "year" is UDUNITS' tropical
# year. (units, target, expected) for a value of 1.
TEST_CASES_COMPOUND_DIFFERENCE_CONVERSIONS = [
    ("degF/foot", "degC/m", (1 / 1.8) / 0.3048),
    ("degC m s-1", "K m s-1", 1),
    ("W m-2 K-1", "W m-2 degC-1", 1),
    ("K2", "degC2", 1),
    ("degF2", "K2", (1 / 1.8) ** 2),
    ("K/year", "degF/year", 1.8),
    ("degC yr-1", "mK/day", 1000 / (31556925.9747 / 86400)),
]

# "With temperature: on_scale, correct conversion can be guaranteed only for
# pure temperature units [...] a value in kg degree_C m-2 can be converted to
# a value in kg K m-2 only if we know separately the values in degree_C and
# kg m-2 of which it is the product."
ON_SCALE_COMPOUND_OFFSET_UNITS = ["kg degC m-2", "degC m s-1", "degF/foot"]

# Same temperature origin in source and target: CF allows the conversion, only
# the other factors change. pint-cf refuses to read the unit instead.
TEST_CASES_ON_SCALE_COMPOUND_SAME_ORIGIN = [
    ("kg degC m-2", "g degC m-2", 10_000),
    ("degC m s-1", "degC km h-1", 36),
    ("degF/foot", "degF/m", 10 / 0.3048),
]

# "A variable must not have a units_metadata attribute [...] if its units do
# not involve a temperature unit" - so it's ignored when reading, and never
# written.
NON_TEMPERATURE_UNITS = ["m", "kg m-2 s-1", "1", "Pa"]

# "these conventions strongly recommend that any variable whose units involve
# a temperature unit should also have a units_metadata attribute"
TEMPERATURE_UNITS = ["degC", "K", "degF/foot", "W m-2 K-1", "K2", "degC m s-1"]

# Writing back what was read must not contradict it ("must be consistent").
# (units, units_metadata, written)
TEST_CASES_ROUND_TRIP = [
    ("degC", ON_SCALE, ON_SCALE),
    ("degC", DIFFERENCE, DIFFERENCE),
    ("degF/foot", DIFFERENCE, DIFFERENCE),
    # Kelvin: pint stores on-scale and difference as the same unit, so the
    # metadata can't be recovered from it - "unknown" doesn't contradict
    # either input.
    ("K", ON_SCALE, UNKNOWN),
    ("K", DIFFERENCE, UNKNOWN),
]

# "If the units_metadata attribute is not present, the data-reader should
# assume temperature: unknown."
UNITS_READ_WITHOUT_METADATA = ["degC", "degC/s", "K", "degF2", "kg degC m-2"]


@pytest.mark.parametrize(
    "value, units, target, expected", TEST_CASES_ON_SCALE_CONVERSIONS
)
def test_on_scale_conversion_applies_offset(
    ureg: pint.UnitRegistry, value: float, units: str, target: str, expected: float
) -> None:
    q = _read(ureg, value, units, ON_SCALE)
    assert q.to(target).magnitude == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    "value, units, target, expected", TEST_CASES_DIFFERENCE_CONVERSIONS
)
def test_difference_conversion_inside_the_block_is_scale_only(
    ureg: pint.UnitRegistry, value: float, units: str, target: str, expected: float
) -> None:
    with CFContext(units_metadata=DIFFERENCE):
        q = ureg.Quantity(value, units)
        assert q.to(target).magnitude == pytest.approx(expected)


@pytest.mark.parametrize(
    "value, units, target, expected", TEST_CASES_DIFFERENCE_CONVERSIONS_AFTER_THE_BLOCK
)
def test_celsius_fahrenheit_difference_never_gets_an_offset_later(
    ureg: pint.UnitRegistry, value: float, units: str, target: str, expected: float
) -> None:
    q = _read(ureg, value, units, DIFFERENCE)
    try:
        converted = q.to(target).magnitude
    except pint.DimensionalityError:
        return  # refusing is CF-safe
    assert converted == pytest.approx(expected)


@pytest.mark.parametrize("target", ["degC", "degF"])
def test_difference_to_on_scale_unit_is_refused(
    ureg: pint.UnitRegistry, target: str
) -> None:
    with pytest.raises(pint.DimensionalityError):
        _read(ureg, 1.5, "degC", DIFFERENCE).to(target)


def test_on_scale_to_difference_unit_is_refused(ureg: pint.UnitRegistry) -> None:
    with pytest.raises(pint.DimensionalityError):
        _read(ureg, 15, "degC", ON_SCALE).to("delta_degC")


@pytest.mark.parametrize(
    "units, target, expected", TEST_CASES_COMPOUND_DIFFERENCE_CONVERSIONS
)
@pytest.mark.parametrize("units_metadata", [DIFFERENCE, UNKNOWN, None])
def test_compound_difference_conversion_is_scale_only(
    ureg: pint.UnitRegistry,
    units_metadata: str | None,
    units: str,
    target: str,
    expected: float,
) -> None:
    with CFContext(units_metadata=units_metadata):
        q = ureg.Quantity(1, units)
        assert q.to(target).magnitude == pytest.approx(expected)


# The same, with the magnitude inside the string, under an explicit
# "difference". Without units_metadata, such a string isn't a CF units
# attribute - one never carries a magnitude (3.1.3) - but a pint
# expression, evaluated as pint documents it (see test_context.py).
# (string, target, expected)
TEST_CASES_COMPOUND_DIFFERENCE_WITH_MAGNITUDE = [
    ("2 degC/s", "mK/s", 2000),
    ("0.02 degC/year", "degF/year", 0.036),
]


@pytest.mark.parametrize(
    "string, target, expected", TEST_CASES_COMPOUND_DIFFERENCE_WITH_MAGNITUDE
)
def test_compound_difference_with_magnitude_in_string_is_scale_only(
    ureg: pint.UnitRegistry, string: str, target: str, expected: float
) -> None:
    with CFContext(units_metadata=DIFFERENCE):
        assert ureg(string).to(target).magnitude == pytest.approx(expected)


@pytest.mark.parametrize("units", ON_SCALE_COMPOUND_OFFSET_UNITS)
def test_on_scale_compound_with_offset_unit_is_refused(
    ureg: pint.UnitRegistry, units: str
) -> None:
    with pytest.raises(ValueError, match="known separately"):
        _read(ureg, 1, units, ON_SCALE)


@_xfail("12", "on_scale compound with degC/degF is refused, not converted")
@pytest.mark.parametrize(
    "units, target, expected", TEST_CASES_ON_SCALE_COMPOUND_SAME_ORIGIN
)
def test_on_scale_compound_with_offset_unit_converts_to_the_same_origin(
    ureg: pint.UnitRegistry, units: str, target: str, expected: float
) -> None:
    with CFContext(units_metadata=ON_SCALE):
        q = ureg.Quantity(10, units)
        assert q.to(target).magnitude == pytest.approx(expected)


def test_on_scale_kelvin_compound_converts_only_to_the_same_origin(
    ureg: pint.UnitRegistry,
) -> None:
    with CFContext(units_metadata=ON_SCALE):
        q = ureg.Quantity(288.15, "kg K m-2")
        assert q.to("g K m-2").magnitude == pytest.approx(288_150)
        with pytest.raises(ValueError, match="known separately"):
            q.to("kg degC m-2")


def test_on_scale_product_of_separately_known_values(ureg: pint.UnitRegistry) -> None:
    q = _read(ureg, 15, "degC", ON_SCALE) * ureg.Quantity(1, "kg m-2")
    assert q.to("kg K m-2").magnitude == pytest.approx(288.15)


@pytest.mark.parametrize("units", NON_TEMPERATURE_UNITS)
@pytest.mark.parametrize("units_metadata", [ON_SCALE, DIFFERENCE, UNKNOWN])
def test_metadata_on_non_temperature_units_is_ignored(
    ureg: pint.UnitRegistry, units_metadata: str, units: str
) -> None:
    q = _read(ureg, 1, units, units_metadata)
    assert q == ureg.Quantity(1, units)
    assert cf_attributes_for(q) == {}


@pytest.mark.parametrize("units", TEMPERATURE_UNITS)
def test_temperature_units_are_written_with_units_metadata(
    ureg: pint.UnitRegistry, units: str
) -> None:
    assert "units_metadata" in cf_attributes_for(_read(ureg, 1, units, DIFFERENCE))


@pytest.mark.parametrize("units, units_metadata, written", TEST_CASES_ROUND_TRIP)
def test_round_trip_does_not_contradict_the_input(
    ureg: pint.UnitRegistry, units: str, units_metadata: str, written: str
) -> None:
    q = _read(ureg, 1, units, units_metadata)
    assert cf_attributes_for(q) == {"units_metadata": written}


@pytest.mark.parametrize("units", UNITS_READ_WITHOUT_METADATA)
def test_absent_units_metadata_is_read_as_unknown(
    ureg: pint.UnitRegistry, units: str
) -> None:
    absent = _read(ureg, 1, units, None)
    unknown = _read(ureg, 1, units, UNKNOWN)
    assert (absent.magnitude, absent.units) == (unknown.magnitude, unknown.units)


def test_cf_example_3_1(ureg: pint.UnitRegistry) -> None:
    """Same units ("degC"), different units_metadata."""
    on_scale = _read(ureg, 15, "degC", ON_SCALE)  # global-mean temperature
    difference = _read(ureg, 1.5, "degC", DIFFERENCE)  # change since 1850

    assert on_scale.to("K").magnitude == pytest.approx(288.15)
    assert difference.to("K").magnitude == pytest.approx(1.5)
    assert on_scale.to("degF").magnitude == pytest.approx(59)
    assert difference.to("delta_degF").magnitude == pytest.approx(2.7)
    assert cf_attributes_for(on_scale) == {"units_metadata": ON_SCALE}
    assert cf_attributes_for(difference) == {"units_metadata": DIFFERENCE}


def test_metadata_applies_to_every_temperature_unit_in_the_block(
    ureg: pint.UnitRegistry,
) -> None:
    """CFContext's contract, which the conversions above rely on: the
    metadata applies to every temperature unit string read inside the
    block, conversion targets included - so a variable with different
    metadata must be converted outside it."""
    t = ureg.Quantity(300.0, "K")  # an on-scale variable, read outside

    with CFContext(units_metadata=DIFFERENCE):
        assert str(t.to("degC").units) == "delta_degree_Celsius"

    assert t.to("degC").magnitude == pytest.approx(26.85)


# Building a quantity with the magnitude inside the string must honor
# units_metadata too.
@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda ureg: ureg("1.5 degC"), id="ureg(str)"),
        pytest.param(lambda ureg: ureg.Quantity("1.5 degC"), id="Quantity(str)"),
    ],
)
def test_difference_honored_with_magnitude_in_string(
    ureg: pint.UnitRegistry, build: object
) -> None:
    with CFContext(units_metadata=DIFFERENCE):
        q = build(ureg)
    assert cf_attributes_for(q) == {"units_metadata": DIFFERENCE}


def test_on_scale_honored_with_magnitude_in_string(ureg: pint.UnitRegistry) -> None:
    with CFContext(units_metadata=ON_SCALE):
        q = ureg("15 degC")
    assert q.to("K").magnitude == pytest.approx(288.15)


# =============================================================================
# 3.1.3 Scale factors and offsets
# =============================================================================

# "The UDUNITS syntax that allows scale factors and offsets to be applied to
# a unit is not supported by this standard, except for case of specifying
# reference time" - such a string must be rejected, never silently read as
# something else.
SCALED_OR_OFFSET_UNITS = [
    "10 m",
    "0.001 kg",
    "1e-3 m",
    "m 1.5",
    "K @ 273.15",
    "K from 273.15",
    "K after 273.15",
    # After a parenthesis, a factor only when spaced or not an integer
    # (an integer glued to ")" is an exponent, as in UDUNITS).
    "(m) 2",
    "(m s) -1",
    "(m)1.5",
]


@pytest.mark.parametrize("units", SCALED_OR_OFFSET_UNITS)
def test_scale_factors_and_offsets_are_rejected(
    ureg: pint.UnitRegistry, units: str
) -> None:
    with pytest.raises(REJECTED):
        ureg.Unit(units)


# =============================================================================
# 3.3 Standard Name
# =============================================================================

# "a variable with a standard_name attribute must have units which are
# physically equivalent [...] to the canonical units" - so every canonical
# unit of the standard name table must be readable, and written back as a
# string that reads back to the same unit.

_CANONICAL_UNITS = [
    line
    for line in (
        Path(__file__).parent / "data" / "cf_standard_name_canonical_units.txt"
    )
    .read_text(encoding="utf-8")
    .splitlines()
    if line and not line.startswith("#")
]

_UNREADABLE_CANONICAL_UNITS = {
    "1e-3": _xfail("7", "a bare number as units is rejected as a scale factor"),
    "1e-6": _xfail("7", "a bare number as units is rejected as a scale factor"),
    # The standard name table itself uses scaled units, which 3.1.3 says CF
    # doesn't support - an inconsistency in CF, not only in pint-cf.
    "1e-3 kg m-2": _xfail("7", "scaled canonical unit"),
    "1e-3 kg s-1": _xfail("7", "scaled canonical unit"),
    "1e-3 s-1": _xfail("7", "scaled canonical unit"),
    "dBZ": _xfail("1", "pint can't prefix a logarithmic unit - decibel branch"),
}

CANONICAL_UNITS = [
    line
    for line in (
        Path(__file__).parent / "data" / "cf_standard_name_canonical_units.txt"
    )
    .read_text(encoding="utf-8")
    .splitlines()
    if line and not line.startswith("#")
]

_UNREADABLE_CANONICAL_UNITS = {
    "1e-3": _xfail("7", "a bare number as units is rejected as a scale factor"),
    "1e-6": _xfail("7", "a bare number as units is rejected as a scale factor"),
    # The standard name table itself uses scaled units, which 3.1.3 says CF
    # doesn't support - an inconsistency in CF, not only in pint-cf.
    "1e-3 kg m-2": _xfail("7", "scaled canonical unit"),
    "1e-3 kg s-1": _xfail("7", "scaled canonical unit"),
    "1e-3 s-1": _xfail("7", "scaled canonical unit"),
    "dBZ": _xfail("1", "pint can't prefix a logarithmic unit - decibel branch"),
}

# Units UDUNITS 2.2.28 (the cf_units build) doesn't define, though the CF
# FAQ does - written back as-is.
_NOT_IN_UDUNITS_2_2_28 = {"dB": _xfail("1", "linear dB from cfunits - decibel branch")}

CANONICAL_UNITS = [
    pytest.param(units, marks=_UNREADABLE_CANONICAL_UNITS.get(units, ()))
    for units in _CANONICAL_UNITS
]
READABLE_CANONICAL_UNITS = [
    units for units in _CANONICAL_UNITS if units not in _UNREADABLE_CANONICAL_UNITS
]


@pytest.mark.parametrize("units", CANONICAL_UNITS)
def test_canonical_units_are_readable(ureg: pint.UnitRegistry, units: str) -> None:
    ureg.Unit(units)


@pytest.mark.parametrize("units", READABLE_CANONICAL_UNITS)
@pytest.mark.parametrize("spec", ["cf", "~cf"])
def test_canonical_units_written_back_read_the_same(
    ureg: pint.UnitRegistry, spec: str, units: str
) -> None:
    unit = ureg.Unit(units)
    assert ureg.Quantity(1, format(unit, spec)).to(unit).magnitude == pytest.approx(1)


# "The value of the units attribute is a string that can be recognized by
# the UDUNITS package" (3.1) - the expected written strings are kept in
# tests/data, generated and checked against the UDUNITS-2 C library by
# tools/write_canonical_units.py. Only "dB" (written "decibel"/"dB") isn't
# recognized by UDUNITS 2.2.28, finding 1, left for the decibel branch.
_WRITTEN_CANONICAL_UNITS = [
    line.split("\t")
    for line in (Path(__file__).parent / "data" / "cf_canonical_units_written.tsv")
    .read_text(encoding="utf-8")
    .splitlines()
    if line and not line.startswith("#")
]


def test_written_canonical_units_cover_every_readable_one() -> None:
    assert [units for units, _, _ in _WRITTEN_CANONICAL_UNITS] == (
        READABLE_CANONICAL_UNITS
    )


@pytest.mark.parametrize(
    "units, expected_cf, expected_short_cf", _WRITTEN_CANONICAL_UNITS
)
def test_canonical_units_written_back_as_checked_against_udunits(
    ureg: pint.UnitRegistry, units: str, expected_cf: str, expected_short_cf: str
) -> None:
    unit = ureg.Unit(units)
    assert format(unit, "cf") == expected_cf
    assert format(unit, "~cf") == expected_short_cf


# =============================================================================
# 4.1 Latitude and 4.2 Longitude coordinates
# =============================================================================

# "The recommended value of the units attribute is the string
# degrees_north. Also accepted are degree_north, degree_N, degrees_N,
# degreeN, and degreesN." - and likewise degrees_east for longitude. UDUNITS
# "only recognizes its size, i.e., 1 degree is defined to be pi/180
# radians". Coordinates with respect to a rotated pole use plain degrees.
LATITUDE_UNITS = [
    "degrees_north",
    "degree_north",
    "degree_N",
    "degrees_N",
    "degreeN",
    "degreesN",
]
LONGITUDE_UNITS = [
    "degrees_east",
    "degree_east",
    "degree_E",
    "degrees_E",
    "degreeE",
    "degreesE",
]
ROTATED_POLE_UNITS = ["degrees"]


@pytest.mark.parametrize("units", LATITUDE_UNITS + LONGITUDE_UNITS + ROTATED_POLE_UNITS)
def test_latitude_longitude_units_are_one_degree(
    ureg: pint.UnitRegistry, units: str
) -> None:
    assert ureg.Quantity(1, units).to("rad").magnitude == pytest.approx(
        DEGREE_IN_RADIANS
    )


# =============================================================================
# 4.3 Vertical coordinate
# =============================================================================

# "units of pressure [...] e.g., bar, millibar, decibar, atmosphere (atm),
# pascal (Pa), and hPa; units of length [...] e.g., meter, metre, m,
# kilometer, km" - and the example uses "meters". Pressure units also tell a
# reader the coordinate is vertical.
PRESSURE_UNITS = [
    "bar",
    "millibar",
    "decibar",
    "atmosphere",
    "atm",
    "pascal",
    "Pa",
    "hPa",
]
LENGTH_UNITS = ["meter", "metre", "m", "kilometer", "km", "meters"]
TEST_CASES_VERTICAL_UNITS = [
    *[(units, "Pa") for units in PRESSURE_UNITS],
    *[(units, "m") for units in LENGTH_UNITS],
]


@pytest.mark.parametrize("units, reference", TEST_CASES_VERTICAL_UNITS)
def test_vertical_coordinate_units(
    ureg: pint.UnitRegistry, units: str, reference: str
) -> None:
    """UDUNITS (and so pint-cf) has no named [pressure] dimension: compare
    with a reference unit's dimensionality instead."""
    assert ureg.Unit(units).dimensionality == ureg.Unit(reference).dimensionality


# =============================================================================
# 4.4.2 Time coordinate units
# =============================================================================

# "day (d), hour (h), minute (min) and second (s). Plural forms are also
# acceptable [...] decimal prefixes [...] e.g. millisecond or ms". "UDUNITS
# defines a year to be exactly 365.242198781 days [...] a month to be exactly
# year/12 [...] a minute as 60 seconds, an hour as 3600 seconds and a day as
# 86400 seconds". (units, seconds)
TEST_CASES_TIME_UNITS = [
    ("second", 1),
    ("s", 1),
    ("seconds", 1),
    ("minute", 60),
    ("min", 60),
    ("minutes", 60),
    ("hour", 3600),
    ("h", 3600),
    ("hours", 3600),
    ("day", 86400),
    ("d", 86400),
    ("days", 86400),
    ("millisecond", 1e-3),
    ("ms", 1e-3),
    ("year", 365.242198781 * 86400),
    ("month", 365.242198781 * 86400 / 12),
]

# A time coordinate's units ("a unit of measure [...] followed by the word
# since and a reference datetime", or one of UDUNITS' alternatives to since)
# are "not physically equivalent to time units that do not include since":
# pint has no notion of a time origin, so pint-cf must reject them rather
# than read them as a plain duration.
TIME_COORDINATE_UNITS = [
    "days since 1990-1-1",
    "days since 1990-1-1 00:00:00Z",
    "seconds since 1992-10-8 15:15:42.5 -6",
    "s since 1972-01-01",
    "hours after 2000-01-01",
    "seconds from 1970-01-01",
    "s ref 1970-01-01",
    "s @ 1970-01-01",
]


@pytest.mark.parametrize("units, seconds", TEST_CASES_TIME_UNITS)
def test_time_units(ureg: pint.UnitRegistry, units: str, seconds: float) -> None:
    assert ureg.Quantity(1, units).to("s").magnitude == pytest.approx(
        seconds, rel=1e-12
    )


@pytest.mark.parametrize("units", TIME_COORDINATE_UNITS)
def test_time_coordinate_units_are_rejected(
    ureg: pint.UnitRegistry, units: str
) -> None:
    with pytest.raises(REJECTED):
        ureg.Unit(units)


# =============================================================================
# 7.5.3 Temporal anomalies
# =============================================================================


def test_anomaly_of_on_scale_temperatures_is_a_difference(
    ureg: pint.UnitRegistry,
) -> None:
    """ "delta_tas has the attribute units_metadata="temperature: difference"
    because it is the difference between two temperatures [...] tas and
    climatological_tas both have the attribute
    units_metadata="temperature: on_scale"\""""
    tas = _read(ureg, np.array([15.2, 16.1]), "degC", ON_SCALE)
    climatological_tas = _read(ureg, 14.0, "degC", ON_SCALE)

    delta_tas = tas - climatological_tas

    assert delta_tas.magnitude == pytest.approx([1.2, 2.1])
    assert cf_attributes_for(delta_tas) == {"units_metadata": DIFFERENCE}


# =============================================================================
# Appendix E Cell methods
# =============================================================================

# range, standard_deviation and variance carry a "*": "if u is a either a
# unit of temperature, or a unit of temperature multiplied by some other
# unit, the temperature in u must be interpreted as a temperature difference.
# Therefore the units_metadata attribute, if present, must have the value
# temperature: difference". variance's units are u2.
_MAX_MINUS_MIN = pytest.param(lambda a: a.max() - a.min(), id="range (max - min)")
_PTP = pytest.param(lambda a: np.ptp(a), id="range (np.ptp)")
_STD = pytest.param(lambda a: np.std(a), id="standard_deviation")
_VAR = pytest.param(lambda a: np.var(a), id="variance")

TEST_CASES_CELL_METHODS_IMPLYING_A_DIFFERENCE = [
    pytest.param("degC", *_MAX_MINUS_MIN.values, id=f"degC-{_MAX_MINUS_MIN.id}"),
    pytest.param(
        "degC",
        *_PTP.values,
        id=f"degC-{_PTP.id}",
        marks=_xfail("17", "pint's np.ptp keeps an on-scale offset unit"),
    ),
    pytest.param("degC", *_STD.values, id=f"degC-{_STD.id}"),
    pytest.param("degC", *_VAR.values, id=f"degC-{_VAR.id}"),
    *[
        pytest.param(
            "K",
            *method.values,
            id=f"K-{method.id}",
            marks=_xfail("13", "a kelvin result is written as 'unknown'"),
        )
        for method in (_MAX_MINUS_MIN, _STD, _VAR)
    ],
]


@pytest.mark.parametrize("units, method", TEST_CASES_CELL_METHODS_IMPLYING_A_DIFFERENCE)
def test_cell_methods_implying_a_difference(
    ureg: pint.UnitRegistry, units: str, method: object
) -> None:
    temperatures = _read(ureg, np.array([10.0, 20.0, 30.0]), units, ON_SCALE)
    result = method(temperatures)
    assert cf_attributes_for(result) == {"units_metadata": DIFFERENCE}
