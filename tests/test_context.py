"""
Tests for how CFContext and cf_attributes_for work.

What CF requires of them is in test_cf_conformance.py; this file covers the
mechanics behind it:

  - CFContext: parsing units_metadata, None, and restoring the previous
    state on exit.
  - The temperature preprocessor, on cf_string_to_pint's output (string
    layer): under "difference", it writes delta_ for every offset
    temperature unit (degree_C, not K), bare or compound, with or without a
    magnitude in the string; under "on_scale" it refuses a compound one.
    Without a context, or with "unknown", it leaves the string alone, so
    pint behaves as it documents.
  - The same through pint's own entry points, on a shared registry -
    including the regression this depends on: pint's `_cache.parse_unit`
    is keyed on the raw string before preprocessors run, so cf_unitregistry()
    disables it (units.py:_NoCache).
  - The on_scale compound-unit error, and the pint bug it steers around.
  - cf_attributes_for, the reverse direction.
"""

import pint
import pytest

from pint_cf import CFContext, cf_attributes_for
from pint_cf.context import (
    _current_temperature_mode,
    _make_temperature_preprocessor,
)
from pint_cf.parser import cf_string_to_pint

ON_SCALE = "temperature: on_scale"
DIFFERENCE = "temperature: difference"
UNKNOWN = "temperature: unknown"

# =============================================================================
# CFContext
# =============================================================================

# (units_metadata, mode)
TEST_CASES_VALID_UNITS_METADATA = [
    (ON_SCALE, "on_scale"),
    (DIFFERENCE, "difference"),
    (UNKNOWN, "unknown"),
    ("temperature:difference", "difference"),
    ("  temperature :  difference  ", "difference"),
    # No units_metadata attribute - CF reads it as "unknown".
    (None, None),
]

INVALID_UNITS_METADATA = [
    "pressure: high",
    "temperature: absolute",
    "on_scale",
    "temperature:",
    "",
]


@pytest.mark.parametrize("units_metadata, mode", TEST_CASES_VALID_UNITS_METADATA)
def test_cfcontext_sets_the_mode(units_metadata: str | None, mode: str | None) -> None:
    with CFContext(units_metadata=units_metadata):
        assert _current_temperature_mode() == mode


@pytest.mark.parametrize("units_metadata", INVALID_UNITS_METADATA)
def test_cfcontext_rejects_invalid_units_metadata(units_metadata: str) -> None:
    with (
        pytest.raises(ValueError, match="Invalid units_metadata"),
        CFContext(units_metadata=units_metadata),
    ):
        pass


def test_cfcontext_none_clears_outer_block() -> None:
    """A variable without units_metadata (CF: unknown) must not inherit the
    metadata of the variable an outer block was opened for."""
    with CFContext(units_metadata=DIFFERENCE), CFContext(units_metadata=None):
        assert _current_temperature_mode() is None


@pytest.mark.parametrize("raises", [False, True], ids=["normal exit", "exception"])
def test_cfcontext_restores_previous_state_on_exit(raises: bool) -> None:
    assert _current_temperature_mode() is None

    try:
        with CFContext(units_metadata=DIFFERENCE):
            assert _current_temperature_mode() == "difference"
            if raises:
                raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert _current_temperature_mode() is None


# =============================================================================
# Temperature preprocessor: string layer
# =============================================================================


def _preprocess(ureg: pint.UnitRegistry, units: str) -> str:
    """cf_string_to_pint followed by the temperature preprocessor - the same
    chain cf_unitregistry() sets up for pint."""
    return _make_temperature_preprocessor(ureg)(cf_string_to_pint(units))


# (units_metadata, input_units, expected_pint_string)
TEST_CASES_TEMPERATURE_MODE_STRING = [
    # delta_ always goes on the canonical name: pint doesn't define it for
    # a plural ("delta_degrees_C") or every other spelling.
    (DIFFERENCE, "degree_C", "delta_degree_Celsius"),
    (DIFFERENCE, "degrees_C", "delta_degree_Celsius"),
    (DIFFERENCE, "degF", "delta_fahrenheit"),
    # Explicit unity power ("**1"/"**+1") must still count as bare: an
    # explicit units_metadata is authoritative and must not be silently
    # dropped just because the pint string happens to contain " ** ".
    (DIFFERENCE, "degree_C**1", "delta_degree_Celsius ** 1"),
    (DIFFERENCE, "degree_C**+1", "delta_degree_Celsius ** +1"),
    # Enclosing parens don't make a unit compound.
    (DIFFERENCE, "(degree_C)", "(delta_degree_Celsius)"),
    (DIFFERENCE, "((degree_C))", "((delta_degree_Celsius))"),
    # A magnitude isn't a unit: "5 degree_C" is still bare.
    (DIFFERENCE, "5 degree_C", "5 * delta_degree_Celsius"),
    (DIFFERENCE, "-0.5 degree_C", "-0.5 * delta_degree_Celsius"),
    (ON_SCALE, "15 degree_C", "15 * degree_C"),
    (None, "15 degree_C", "15 * degree_C"),
    # Compound under "difference": the metadata applies to every offset
    # unit, with or without a magnitude.
    (DIFFERENCE, "degree_C/s", "delta_degree_Celsius / s"),
    (DIFFERENCE, "degree_C**2", "delta_degree_Celsius ** 2"),
    (DIFFERENCE, "degree_C**-1", "delta_degree_Celsius ** -1"),
    (DIFFERENCE, "degrees_C m-2", "delta_degree_Celsius * m ** -2"),
    (DIFFERENCE, "2 degree_C/s", "2 * delta_degree_Celsius / s"),
    (DIFFERENCE, "degF degC", "delta_fahrenheit * delta_degree_Celsius"),
    # Only whole unit names are rewritten, not other names containing one.
    (DIFFERENCE, "degC kdegC_x", "delta_degree_Celsius * kdegC_x"),
    # Without a context, or with "unknown", nothing is rewritten: pint
    # applies its own rules (as_delta for a unit string).
    (UNKNOWN, "degree_C/s", "degree_C / s"),
    (None, "degree_C/s", "degree_C / s"),
    (None, "2 degree_C/s", "2 * degree_C / s"),
    # Idempotency: pint can re-apply its preprocessors to an
    # already-processed string - must not double-prefix into
    # "delta_delta_degree_C".
    (DIFFERENCE, "delta_degree_C", "delta_degree_C"),
    (DIFFERENCE, "delta_degree_C/s", "delta_degree_C / s"),
    # No offset (kelvin, rankine, prefixed kelvin): on_scale and difference
    # are the same pint unit, so the mode has nothing to change - there is
    # no delta_K to resolve to.
    (DIFFERENCE, "K", "K"),
    (DIFFERENCE, "degree_R", "degree_R"),
    (DIFFERENCE, "mK", "mK"),
    (DIFFERENCE, "K s-1", "K * s ** -1"),
    # Not a temperature at all: CF forbids units_metadata here, but this is
    # a reader, not a validator - ignored rather than rejected.
    (DIFFERENCE, "m", "m"),
    (DIFFERENCE, "1", "1"),
    # Logarithmic units are non-multiplicative in pint too, but they're not
    # temperatures - must not become "delta_B".
    (DIFFERENCE, "B", "B"),
    (DIFFERENCE, "B m-1", "B * m ** -1"),
    # CF allows on_scale on a compound unit; without an offset temperature
    # unit in it, there's nothing to reject.
    (ON_SCALE, "K m-1", "K * m ** -1"),
    (ON_SCALE, "W m-2 K-1", "W * m ** -2 * K ** -1"),
    (ON_SCALE, "m s-1", "m * s ** -1"),
    (ON_SCALE, "degree_C", "degree_C"),
    (ON_SCALE, "degree_C**1", "degree_C ** 1"),
    (UNKNOWN, "degree_C", "degree_C"),
    (None, "degree_C", "degree_C"),
]

ON_SCALE_COMPOUND_OFFSET_UNITS = ["degree_C/s", "kg degree_C m-2", "2 degree_C/s"]


@pytest.mark.parametrize(
    "units_metadata, input_units, expected", TEST_CASES_TEMPERATURE_MODE_STRING
)
def test_temperature_mode_applied_to_string(
    ureg: pint.UnitRegistry,
    units_metadata: str | None,
    input_units: str,
    expected: str,
) -> None:
    with CFContext(units_metadata=units_metadata):
        assert _preprocess(ureg, input_units) == expected


def test_no_context_at_all_changes_nothing(ureg: pint.UnitRegistry) -> None:
    assert _preprocess(ureg, "degree_C") == "degree_C"


def test_cf_string_to_pint_ignores_context() -> None:
    """cf_string_to_pint is a pure syntax translation - the temperature mode
    is applied by a separate preprocessor, not by it."""
    with CFContext(units_metadata=DIFFERENCE):
        assert cf_string_to_pint("degree_C") == "degree_C"


@pytest.mark.parametrize("units", ON_SCALE_COMPOUND_OFFSET_UNITS)
def test_on_scale_compound_offset_unit_raises(
    ureg: pint.UnitRegistry, units: str
) -> None:
    with (
        pytest.raises(ValueError, match=r"on_scale.*compound"),
        CFContext(units_metadata=ON_SCALE),
    ):
        _preprocess(ureg, units)


# =============================================================================
# Through pint's own entry points, on a shared registry
# =============================================================================

# (units_metadata, units, expected_units)
TEST_CASES_TEMPERATURE_MODE_PINT = [
    (DIFFERENCE, "degree_C", "delta_degree_Celsius"),
    (ON_SCALE, "degree_C", "degree_Celsius"),
    # Regression: the delta_ of a plural spelling was undefined.
    (DIFFERENCE, "degrees_C", "delta_degree_Celsius"),
    (DIFFERENCE, "degree_C/s", "delta_degree_Celsius / second"),
    (DIFFERENCE, "degree_C**2", "delta_degree_Celsius ** 2"),
    # Regression: must actually be parseable by pint, not just produce the
    # right intermediate string - "(degree_C)" previously became the invalid
    # "delta_(degree_C)" and raised UndefinedUnitError.
    (DIFFERENCE, "(degree_C)", "delta_degree_Celsius"),
    (DIFFERENCE, "((degree_C))", "delta_degree_Celsius"),
    # Regression: "K" became "delta_K" and raised UndefinedUnitError - the
    # canonical CF temperature anomaly.
    (DIFFERENCE, "K", "kelvin"),
    (DIFFERENCE, "m", "meter"),
    # Regression: any compound unit raised ValueError under on_scale, even
    # without an offset temperature unit in it.
    (ON_SCALE, "K m-1", "kelvin / meter"),
    (ON_SCALE, "W m-2 K-1", "watt / kelvin / meter ** 2"),
]

_BUILDERS = {
    "Quantity": lambda ureg, units: ureg.Quantity(1, units).units,
    "ureg(str)": lambda ureg, units: ureg(units).units,
    "Unit": lambda ureg, units: ureg.Unit(units),
}

CASES_THROUGH_PINT = [
    pytest.param(
        units_metadata,
        units,
        expected,
        build,
        id=f"{build_id}-{units_metadata}-{units}",
    )
    for units_metadata, units, expected in TEST_CASES_TEMPERATURE_MODE_PINT
    for build_id, build in _BUILDERS.items()
]

# Without a context, a unit string follows pint's as_delta rule - the
# UDUNITS assumption: a compound offset unit is a difference.
UNIT_STRING_BUILDERS = {k: v for k, v in _BUILDERS.items() if k != "ureg(str)"}


@pytest.mark.parametrize("units_metadata", [UNKNOWN, None])
@pytest.mark.parametrize(
    "build", UNIT_STRING_BUILDERS.values(), ids=UNIT_STRING_BUILDERS
)
@pytest.mark.parametrize(
    "units, expected",
    [
        ("degree_C", "degree_Celsius"),
        ("degree_C/s", "delta_degree_Celsius / second"),
        ("degree_C**2", "delta_degree_Celsius ** 2"),
    ],
)
def test_unknown_unit_string_follows_pint_as_delta(
    ureg: pint.UnitRegistry,
    units_metadata: str | None,
    build: object,
    units: str,
    expected: str,
) -> None:
    with CFContext(units_metadata=units_metadata):
        assert str(build(ureg, units)) == expected


@pytest.mark.parametrize("units_metadata", [UNKNOWN, None])
def test_unknown_respects_as_delta_false(
    ureg: pint.UnitRegistry, units_metadata: str | None
) -> None:
    """An explicit as_delta=False is the caller's choice: not overridden."""
    with CFContext(units_metadata=units_metadata):
        units = ureg.parse_units("degC/s", as_delta=False)
    assert str(units) == "degree_Celsius / second"


def test_unknown_expression_string_follows_pint_arithmetic(
    ureg: pint.UnitRegistry,
) -> None:
    """ureg(str)/Quantity(str) evaluate a pint expression, not a CF units
    attribute (which never carries a magnitude, CF 3.1.3). Without a
    context pint-cf leaves pint's documented arithmetic alone: with
    autoconvert_offset_to_baseunit=True, "2 degC/s" is 2 degC, converted
    on-scale to kelvin, divided by a second (CODE_REVIEW 18). Read CF data
    with ureg.Quantity(values, units) instead."""
    assert ureg("2 degC/s").to("K/s").magnitude == pytest.approx(275.15)
    assert ureg.Quantity(2, "degC/s").to("K/s").magnitude == pytest.approx(2)


@pytest.mark.parametrize("units_metadata, units, expected, build", CASES_THROUGH_PINT)
def test_temperature_mode_applied_through_pint(
    ureg: pint.UnitRegistry,
    units_metadata: str | None,
    units: str,
    expected: str,
    build: object,
) -> None:
    with CFContext(units_metadata=units_metadata):
        assert str(build(ureg, units)) == expected


# Under a context, a magnitude in the string - ureg(str), Quantity(str) -
# must read the same as a magnitude passed separately (CODE_REVIEW 3).
# (units_metadata, string, expected_magnitude, expected_units)
TEST_CASES_MAGNITUDE_IN_STRING = [
    (DIFFERENCE, "5 degC", 5, "delta_degree_Celsius"),
    (ON_SCALE, "15 degC", 15, "degree_Celsius"),
    (None, "15 degC", 15, "degree_Celsius"),
    (DIFFERENCE, "2 degC/s", 2, "delta_degree_Celsius / second"),
    (DIFFERENCE, "0.02 degC/year", 0.02, "delta_degree_Celsius / tropical_year"),
]


@pytest.mark.parametrize(
    "units_metadata, string, magnitude, units", TEST_CASES_MAGNITUDE_IN_STRING
)
@pytest.mark.parametrize(
    "build",
    [lambda ureg, s: ureg(s), lambda ureg, s: ureg.Quantity(s)],
    ids=["ureg(str)", "Quantity(str)"],
)
def test_magnitude_in_string_reads_like_separate_magnitude(
    ureg: pint.UnitRegistry,
    units_metadata: str | None,
    string: str,
    magnitude: float,
    units: str,
    build: object,
) -> None:
    with CFContext(units_metadata=units_metadata):
        q = build(ureg, string)
    assert q.magnitude == pytest.approx(magnitude)
    assert str(q.units) == units


# Every UDUNITS spelling of an offset temperature unit has a delta_
# counterpart, plurals included: pint's own automatic plurals are disabled,
# so the registry must spell each one out (tools/xmlrd.py:_get_delta_alias).
DELTA_SPELLINGS = {
    "delta_degree_Celsius": [
        "degree_Celsius",
        "degrees_Celsius",
        "celsius",
        "celsiuses",
        "degree_C",
        "degrees_C",
        "degreeC",
        "degreesC",
        "deg_C",
        "degs_C",
        "degC",
        "degsC",
    ],
    "delta_fahrenheit": [
        "fahrenheit",
        "fahrenheits",
        "degree_fahrenheit",
        "degrees_fahrenheit",
        "degreeF",
        "degreesF",
        "degree_F",
        "degrees_F",
        "degF",
        "degsF",
        "deg_F",
        "degs_F",
    ],
}


@pytest.mark.parametrize(
    "units, expected",
    [
        pytest.param(f"delta_{name}", expected, id=f"delta_{name}")
        for expected, names in DELTA_SPELLINGS.items()
        for name in names
    ],
)
def test_every_offset_unit_spelling_has_a_delta(
    ureg: pint.UnitRegistry, units: str, expected: str
) -> None:
    assert str(ureg.Unit(units)) == expected


@pytest.mark.parametrize("units", ["delta_degree_Cs", "delta_degreeCs", "delta_deg_Cs"])
def test_no_invented_delta_plurals(ureg: pint.UnitRegistry, units: str) -> None:
    """Regression: the generator used to build delta_ plurals by appending
    "s" to the singular, instead of using the XML's own plural."""
    with pytest.raises(pint.UndefinedUnitError):
        ureg.Unit(units)


def test_repeated_parsing_of_same_string_survives_pint_cache(
    ureg: pint.UnitRegistry,
) -> None:
    """pint caches parse_unit results keyed on the raw string, before
    preprocessors run. Parsing the SAME raw string plain, then under
    "difference", then plain again on the SAME registry must not return a
    stale result from an earlier call."""
    assert str(ureg.Quantity(1, "degree_C").units) == "degree_Celsius"
    with CFContext(units_metadata=DIFFERENCE):
        assert str(ureg.Quantity(1, "degree_C").units) == "delta_degree_Celsius"
    assert str(ureg.Quantity(1, "degree_C").units) == "degree_Celsius"


# =============================================================================
# The on_scale compound-unit error
# =============================================================================


def test_on_scale_compound_error_points_to_a_working_route(
    ureg: pint.UnitRegistry,
) -> None:
    """The route the ValueError suggests must actually work: multiplying
    separately known values converts the on-scale temperature to kelvin
    first, which is correct."""
    with (
        pytest.raises(ValueError, match="known separately") as excinfo,
        CFContext(units_metadata=ON_SCALE),
    ):
        ureg.Quantity(10, "kg degC m-2")
    assert "ureg.Quantity(t, 'degC') * ureg.Quantity(x, 'kg m-2')" in str(excinfo.value)

    q = ureg.Quantity(10, "degC") * ureg.Quantity(1, "kg m-2")
    assert q.to("g K m-2").magnitude == pytest.approx(283_150)


def test_forced_on_scale_compound_unit_converts_wrongly(
    ureg: pint.UnitRegistry,
) -> None:
    """Why that ValueError doesn't suggest parse_units(units,
    as_delta=False): under
    autoconvert_offset_to_baseunit=True, pint (0.25 and 0.26) silently
    drops the scale factor converting such a unit - 10 kg degC m-2 becomes
    10, not 10000, g degC m-2 (CODE_REVIEW 12). If this starts failing, pint
    fixed it: revisit the ValueError's message."""
    q = ureg.Quantity(10, ureg.parse_units("kg degC m-2", as_delta=False))
    converted = q.to(ureg.parse_units("g degC m-2", as_delta=False))
    assert converted.magnitude == pytest.approx(10)


# =============================================================================
# cf_attributes_for
# =============================================================================

# (units, expected)
TEST_CASES_CF_ATTRIBUTES_FOR = [
    ("degree_Celsius", {"units_metadata": ON_SCALE}),
    ("delta_degree_Celsius", {"units_metadata": DIFFERENCE}),
    ("fahrenheit", {"units_metadata": ON_SCALE}),
    ("delta_fahrenheit", {"units_metadata": DIFFERENCE}),
    ("degree_Celsius / second", {"units_metadata": DIFFERENCE}),
    ("degree_Celsius * meter", {"units_metadata": DIFFERENCE}),
    ("meter", {}),
    ("second", {}),
    # Kelvin/Rankine have no offset, so no delta_ counterpart exists either -
    # on_scale and difference are numerically identical for them and cannot
    # be recovered from the Unit alone.
    ("kelvin", {"units_metadata": UNKNOWN}),
    ("kelvin ** 2", {"units_metadata": UNKNOWN}),
    ("kelvin / second", {"units_metadata": UNKNOWN}),
    ("degree_rankine", {"units_metadata": UNKNOWN}),
]

# A pint unit can't carry "unknown": with units_metadata absent or
# "unknown", pint applies the UDUNITS rule (which CF quotes as guidance
# only), and cf_attributes_for reports that guess as if it were known - a
# documented limitation. (units, udunits_guess)
TEST_CASES_UDUNITS_GUESS = [
    ("degree_C", ON_SCALE),
    ("degree_C/s", DIFFERENCE),
    ("degree_C2", DIFFERENCE),
]


@pytest.mark.parametrize("units, expected", TEST_CASES_CF_ATTRIBUTES_FOR)
@pytest.mark.parametrize(
    "as_quantity", [False, True], ids=["from Unit", "from Quantity"]
)
def test_cf_attributes_for(
    ureg: pint.UnitRegistry,
    units: str,
    expected: dict[str, str],
    as_quantity: bool,
) -> None:
    unit = ureg.Unit(units)
    assert cf_attributes_for(ureg.Quantity(1, unit) if as_quantity else unit) == (
        expected
    )


@pytest.mark.parametrize("units, udunits_guess", TEST_CASES_UDUNITS_GUESS)
@pytest.mark.parametrize("units_metadata", [None, UNKNOWN])
def test_cf_attributes_for_reports_the_udunits_guess_for_unknown(
    ureg: pint.UnitRegistry,
    units_metadata: str | None,
    units: str,
    udunits_guess: str,
) -> None:
    with CFContext(units_metadata=units_metadata):
        q = ureg.Quantity(1, units)
    assert cf_attributes_for(q) == {"units_metadata": udunits_guess}
