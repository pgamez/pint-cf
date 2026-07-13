"""
Tests for CF units_metadata support (CFContext, cf_attributes_for).

Covers, in order:
  - CFContext validation (accepts/rejects, reset behavior).
  - cf_string_to_pint (string layer): only forces delta_ for a BARE
    temperature unit under "temperature: difference" - it never needs to
    handle the compound case, because pint's own default `as_delta=True`
    already applies UDUNITS' heuristic (delta_ whenever a non-multiplicative
    unit is raised to a power != 1, or combined with another unit).
  - Native pint calls (ureg.Quantity(...), ureg(...)) under an active
    CFContext, using the SAME registry across calls with different (or no)
    context. This exercises the regression this feature depends on: pint's
    `_cache.parse_unit` memoizes a parsed result keyed on the raw string,
    before preprocessors run - cf_unitregistry() disables that specific
    cache (see units.py:_NoCache) so a later call with the same raw string
    isn't served a stale result from an earlier, differently-contexted call.
  - cf_attributes_for (the reverse direction): Kelvin/Rankine have no
    offset, so they have no delta_ counterpart either - on_scale and
    difference are numerically identical for them and genuinely can't be
    recovered from a Unit/Quantity alone. That case must resolve to
    "temperature: unknown", not be guessed as "difference" just because
    the unit happens to be multiplicative (a bug found in an earlier
    attempt at this feature, on the units_metadata branch).
"""

import pint
import pytest

from pint_cf import CFContext, cf_attributes_for, cf_unitregistry
from pint_cf.context import _current_temperature_mode, _strip_enclosing_parens
from pint_cf.parser import cf_string_to_pint

# =============================================================================
# CFContext validation
# =============================================================================

VALID_UNITS_METADATA = [
    "temperature: on_scale",
    "temperature: difference",
    "temperature: unknown",
    "temperature:difference",
    "  temperature :  difference  ",
]

INVALID_UNITS_METADATA = [
    "pressure: high",
    "temperature: absolute",
    "on_scale",
    "temperature:",
    "",
]


@pytest.mark.parametrize("units_metadata", VALID_UNITS_METADATA)
def test_cfcontext_accepts_valid_units_metadata(units_metadata: str) -> None:
    with CFContext(units_metadata=units_metadata):
        assert _current_temperature_mode() in {"on_scale", "difference", "unknown"}


@pytest.mark.parametrize("units_metadata", INVALID_UNITS_METADATA)
def test_cfcontext_rejects_invalid_units_metadata(units_metadata: str) -> None:
    with pytest.raises(ValueError, match="Invalid units_metadata"):
        with CFContext(units_metadata=units_metadata):
            pass


def test_cfcontext_none_is_a_no_op() -> None:
    with CFContext(units_metadata=None):
        assert _current_temperature_mode() is None


def test_cfcontext_resets_after_exit() -> None:
    assert _current_temperature_mode() is None

    with CFContext(units_metadata="temperature: difference"):
        assert _current_temperature_mode() == "difference"

    assert _current_temperature_mode() is None


def test_cfcontext_resets_on_exception() -> None:
    with pytest.raises(RuntimeError):
        with CFContext(units_metadata="temperature: difference"):
            raise RuntimeError("boom")

    assert _current_temperature_mode() is None


# =============================================================================
# cf_string_to_pint: string-layer behavior
# =============================================================================

# (units_metadata, input_units, expected_pint_string)
TEST_CASES_TEMPERATURE_MODE_STRING = [
    ("temperature: difference", "degree_C", "delta_degree_C"),
    # Explicit unity power ("**1"/"**+1") must still count as bare: an
    # explicit units_metadata is authoritative and must not be silently
    # dropped just because the pint string happens to contain " ** ".
    ("temperature: difference", "degree_C**1", "delta_degree_C ** 1"),
    ("temperature: difference", "degree_C**+1", "delta_degree_C ** +1"),
    # Compound expressions are left untouched here: pint's own as_delta=True
    # default already adds delta_ once parsed, so acting on the string too
    # would double up on it.
    ("temperature: difference", "degree_C/s", "degree_C / s"),
    ("temperature: difference", "degree_C**2", "degree_C ** 2"),
    ("temperature: difference", "degree_C**-1", "degree_C ** -1"),
    # A bare unit stays bare regardless of enclosing parens - prefixing
    # "delta_" onto the string unstripped would produce invalid syntax like
    # "delta_(degree_C)".
    ("temperature: difference", "(degree_C)", "delta_degree_C"),
    ("temperature: difference", "((degree_C))", "delta_degree_C"),
    # Idempotency: cf_string_to_pint can run more than once on the same
    # string within one CFContext (pint re-applies its preprocessors
    # internally) - must not double-prefix into "delta_delta_degree_C".
    ("temperature: difference", "delta_degree_C", "delta_degree_C"),
    ("temperature: on_scale", "degree_C", "degree_C"),
    ("temperature: on_scale", "degree_C**1", "degree_C ** 1"),
    (None, "degree_C", "degree_C"),
    (None, "degree_C/s", "degree_C / s"),
    ("temperature: unknown", "degree_C", "degree_C"),
    ("temperature: unknown", "degree_C/s", "degree_C / s"),
]


@pytest.mark.parametrize(
    "units_metadata, input_units, expected", TEST_CASES_TEMPERATURE_MODE_STRING
)
def test_temperature_mode_applied_to_string(
    units_metadata: str | None, input_units: str, expected: str
) -> None:
    with CFContext(units_metadata=units_metadata):
        assert cf_string_to_pint(input_units) == expected


def test_no_active_context_behaves_as_before() -> None:
    """Same as the (None, "degree_C", "degree_C") case above, but without
    even entering CFContext - confirms the feature is fully opt-in."""
    assert cf_string_to_pint("degree_C") == "degree_C"


def test_on_scale_on_compound_unit_raises() -> None:
    with pytest.raises(ValueError, match="on_scale.*compound"):
        with CFContext(units_metadata="temperature: on_scale"):
            cf_string_to_pint("degree_C/s")


# =============================================================================
# Native pint calls under CFContext, on a shared registry
# =============================================================================


@pytest.fixture(scope="module")
def ureg() -> pint.UnitRegistry:
    return cf_unitregistry()


# (units_metadata, units, expected_units_str)
TEST_CASES_TEMPERATURE_MODE_QUANTITY = [
    ("temperature: difference", "degree_C", "delta_degree_Celsius"),
    ("temperature: on_scale", "degree_C", "degree_Celsius"),
    ("temperature: difference", "degree_C/s", "delta_degree_Celsius / second"),
    (None, "degree_C**2", "delta_degree_Celsius ** 2"),
    # Regression: must actually be parseable by pint, not just produce the
    # right intermediate string - "(degree_C)" previously became the invalid
    # "delta_(degree_C)" and raised UndefinedUnitError.
    ("temperature: difference", "(degree_C)", "delta_degree_Celsius"),
    ("temperature: difference", "((degree_C))", "delta_degree_Celsius"),
]


@pytest.mark.parametrize(
    "units_metadata, units, expected", TEST_CASES_TEMPERATURE_MODE_QUANTITY
)
def test_temperature_mode_applied_to_quantity(
    ureg: pint.UnitRegistry, units_metadata: str | None, units: str, expected: str
) -> None:
    with CFContext(units_metadata=units_metadata):
        q = ureg.Quantity(1, units)
    assert str(q.units) == expected


def test_quantity_on_scale_on_compound_unit_raises(ureg: pint.UnitRegistry) -> None:
    with pytest.raises(ValueError, match="on_scale.*compound"):
        with CFContext(units_metadata="temperature: on_scale"):
            ureg.Quantity(1, "degree_C/s")


def test_ureg_call_form_also_honors_context(ureg: pint.UnitRegistry) -> None:
    with CFContext(units_metadata="temperature: difference"):
        q = ureg("degree_C")
    assert str(q.units) == "delta_degree_Celsius"


def test_repeated_parsing_of_same_string_survives_pint_cache(
    ureg: pint.UnitRegistry,
) -> None:
    """Regression test: pint caches parse_unit results keyed on the raw
    string, before preprocessors run. Parsing the SAME raw string plain and
    then under "difference" (and back) on the SAME registry must not return
    a stale cached result from an earlier call."""
    plain_1 = ureg.Quantity(1, "degree_C")
    assert str(plain_1.units) == "degree_Celsius"

    with CFContext(units_metadata="temperature: difference"):
        difference = ureg.Quantity(1, "degree_C")
    assert str(difference.units) == "delta_degree_Celsius"

    plain_2 = ureg.Quantity(1, "degree_C")
    assert str(plain_2.units) == "degree_Celsius"


# =============================================================================
# cf_attributes_for: the reverse direction (Unit/Quantity -> CF attributes)
# =============================================================================

# (units, expected)
TEST_CASES_CF_ATTRIBUTES_FOR = [
    ("degree_Celsius", {"units_metadata": "temperature: on_scale"}),
    ("delta_degree_Celsius", {"units_metadata": "temperature: difference"}),
    ("fahrenheit", {"units_metadata": "temperature: on_scale"}),
    ("delta_fahrenheit", {"units_metadata": "temperature: difference"}),
    ("degree_Celsius / second", {"units_metadata": "temperature: difference"}),
    ("degree_Celsius * meter", {"units_metadata": "temperature: difference"}),
    ("meter", {}),
    ("second", {}),
    # Kelvin/Rankine have no offset, so no delta_ counterpart exists either -
    # on_scale and difference are numerically identical for them and cannot
    # be recovered from the Unit alone.
    ("kelvin", {"units_metadata": "temperature: unknown"}),
    ("kelvin ** 2", {"units_metadata": "temperature: unknown"}),
    ("kelvin / second", {"units_metadata": "temperature: unknown"}),
    ("degree_rankine", {"units_metadata": "temperature: unknown"}),
]


@pytest.mark.parametrize("units, expected", TEST_CASES_CF_ATTRIBUTES_FOR)
def test_cf_attributes_for_unit(
    ureg: pint.UnitRegistry, units: str, expected: dict[str, str]
) -> None:
    assert cf_attributes_for(ureg.Unit(units)) == expected


def test_cf_attributes_for_quantity(ureg: pint.UnitRegistry) -> None:
    """Accepts a Quantity directly (extracting .units), not just a Unit."""
    q = ureg.Quantity(1, "delta_degree_Celsius")
    assert cf_attributes_for(q) == {"units_metadata": "temperature: difference"}


def test_cf_attributes_for_round_trips_with_cfcontext(
    ureg: pint.UnitRegistry,
) -> None:
    with CFContext(units_metadata="temperature: difference"):
        q = ureg.Quantity(1, "degree_C")

    assert cf_attributes_for(q) == {"units_metadata": "temperature: difference"}


# =============================================================================
# _strip_enclosing_parens
# =============================================================================


@pytest.mark.parametrize(
    "pint_string, expected",
    [
        ("degree_C", "degree_C"),
        ("(degree_C)", "degree_C"),
        ("((degree_C))", "degree_C"),
        ("(((degree_C)))", "degree_C"),
        # Leading "(" closes before the string ends - not fully enclosing,
        # must be left untouched (stripping it would break the expression).
        ("(m) * (s)", "(m) * (s)"),
        ("(m) / s", "(m) / s"),
    ],
)
def test_strip_enclosing_parens(pint_string: str, expected: str) -> None:
    assert _strip_enclosing_parens(pint_string) == expected
