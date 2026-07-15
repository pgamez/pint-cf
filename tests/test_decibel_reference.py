"""
Tests for CF standard_name-driven decibel reference levels (CFContext,
cf_attributes_for).

CF's own FAQ says the physical reference level a decibel value is relative
to "is specified in the standard names that use this canonical unit", not
by the unit string alone. `CFContext(standard_name=...)` resolves a bare
dB/decibel string to the pre-registered pint unit that carries that
standard name's reference level and dimension - see
pint_cf.context._apply_standard_name_reference. The pint side of that
mapping is a private, leading-underscore unit name (e.g.
`_dB_sound_pressure_level_in_air`) - it's pint-cf's own invention, not a real
CF unit, since CF only defines the standard_name, not a unit for it.

Covers, in order:
  - Plain dB/decibel behavior is unaffected with no active context, or an
    unrecognized standard_name (fully opt-in, same as units_metadata).
  - cf_string_to_pint (string layer): only a bare dB/decibel/decibels is
    resolved; compound expressions (already carrying their own reference,
    or nonsensical like "dB / s") are left untouched.
  - Native pint calls: physical conversion actually matches the CF standard
    name table's reference levels.
  - Formatting: a resolved unit still writes back out as "dB"/"decibel",
    not its internal pint unit name.
  - cf_attributes_for (the reverse direction): a resolved unit's own private
    name maps back to exactly one standard_name.
"""

import math
from typing import NamedTuple

import pint
import pytest

from pint_cf import CFContext, cf_attributes_for, cf_unitregistry
from pint_cf.parser import cf_string_to_pint


class ReferenceLevel(NamedTuple):
    """One row of the CF standard name table (CF FAQ, "Units decibel
    (bel)"). `internal_unit` is pint-cf's own, private (leading-underscore)
    invention - CF only defines the standard_name, not a unit for it."""

    standard_name: str
    internal_unit: str
    reference_unit: str
    reference_value: float
    logfactor: int


# =============================================================================
# Reference levels from the CF standard name table
# =============================================================================

REFERENCE_LEVELS = [
    ReferenceLevel(
        "sound_intensity_level_in_air",
        "_dB_sound_intensity_level_in_air",
        "watt/meter**2",
        1e-12,
        10,
    ),
    ReferenceLevel(
        "sound_intensity_level_in_water",
        "_dB_sound_intensity_level_in_water",
        "watt/meter**2",
        6.7e-19,
        10,
    ),
    ReferenceLevel(
        "sound_pressure_level_in_air",
        "_dB_sound_pressure_level_in_air",
        "pascal",
        2e-5,
        20,
    ),
    ReferenceLevel(
        "sound_pressure_level_in_water",
        "_dB_sound_pressure_level_in_water",
        "pascal",
        1e-6,
        20,
    ),
]

UNRECOGNIZED_STANDARD_NAMES = [None, "air_temperature", "sound_pressure_level_in_soup"]

# =============================================================================
# Opt-in: plain dB/decibel is unaffected by default
# =============================================================================


@pytest.mark.parametrize("standard_name", UNRECOGNIZED_STANDARD_NAMES)
def test_unrecognized_standard_name_is_a_no_op(
    ureg: pint.UnitRegistry, standard_name: str | None
) -> None:
    with CFContext(standard_name=standard_name):
        q = ureg.Quantity(3, "dB")
    assert str(q.units) == "decibel"
    assert q.to("dimensionless").magnitude == 3


def test_no_active_context_behaves_as_before() -> None:
    assert cf_string_to_pint("dB") == "dB"
    assert cf_string_to_pint("decibel") == "decibel"


# =============================================================================
# cf_string_to_pint: string-layer behavior
# =============================================================================


@pytest.mark.parametrize("case", REFERENCE_LEVELS, ids=lambda c: c.standard_name)
@pytest.mark.parametrize("bare_form", ["dB", "decibel", "decibels"])
def test_standard_name_resolves_bare_form_to_string(
    case: ReferenceLevel, bare_form: str
) -> None:
    with CFContext(standard_name=case.standard_name):
        assert cf_string_to_pint(bare_form) == case.internal_unit


@pytest.mark.parametrize("case", REFERENCE_LEVELS, ids=lambda c: c.standard_name)
def test_standard_name_leaves_compound_dB_expression_untouched(
    case: ReferenceLevel,
) -> None:
    """A compound dB expression either already carries its own explicit
    reference (e.g. UDUNITS `lg(re 1 uPa)`) or isn't a plain decibel value
    at all - standard_name must not override either case."""
    with CFContext(standard_name=case.standard_name):
        assert cf_string_to_pint("dB/s") == "dB / s"
        assert (
            cf_string_to_pint("lg(re 1 uPa)") == "1 * uPa; logbase: 10; logfactor: 10"
        )


def test_standard_name_does_not_affect_bel() -> None:
    """CF's standard name table only ever pairs these standard names with
    dB, never bel - "bel" is deliberately left as the plain unit."""
    with CFContext(standard_name="sound_pressure_level_in_air"):
        assert cf_string_to_pint("bel") == "bel"


# =============================================================================
# Native pint calls: physical conversion matches the CF reference levels
# =============================================================================


@pytest.mark.parametrize("case", REFERENCE_LEVELS, ids=lambda c: c.standard_name)
def test_standard_name_applied_to_quantity(
    ureg: pint.UnitRegistry, case: ReferenceLevel
) -> None:
    with CFContext(standard_name=case.standard_name):
        q = ureg.Quantity(74, "dB")

    assert str(q.units) == case.internal_unit

    physical = q.to(case.reference_unit).magnitude
    db = case.logfactor * math.log10(physical / case.reference_value)
    assert db == pytest.approx(74)


def test_repeated_parsing_of_same_string_survives_pint_cache(
    ureg: pint.UnitRegistry,
) -> None:
    """Regression test, mirroring the equivalent temperature-mode test: the
    SAME raw string ("dB") must resolve differently across calls with
    different (or no) active context on the SAME registry."""
    plain_1 = ureg.Quantity(3, "dB")
    assert str(plain_1.units) == "decibel"

    with CFContext(standard_name="sound_pressure_level_in_air"):
        resolved = ureg.Quantity(74, "dB")
    assert str(resolved.units) == "_dB_sound_pressure_level_in_air"

    plain_2 = ureg.Quantity(3, "dB")
    assert str(plain_2.units) == "decibel"


# =============================================================================
# Formatting: a resolved unit still writes back out as a CF dB unit
# =============================================================================


@pytest.mark.parametrize("case", REFERENCE_LEVELS, ids=lambda c: c.standard_name)
def test_resolved_unit_formats_back_as_dB(
    ureg: pint.UnitRegistry, case: ReferenceLevel
) -> None:
    with CFContext(standard_name=case.standard_name):
        q = ureg.Quantity(74, "dB")

    assert format(q, "cf") == "74 decibel"
    assert format(q, "~cf") == "74 dB"


# =============================================================================
# cf_attributes_for: the reverse direction (Unit/Quantity -> standard_name)
# =============================================================================


@pytest.mark.parametrize("case", REFERENCE_LEVELS, ids=lambda c: c.standard_name)
def test_cf_attributes_for_resolved_unit(
    ureg: pint.UnitRegistry, case: ReferenceLevel
) -> None:
    assert cf_attributes_for(ureg.Unit(case.internal_unit)) == {
        "standard_name": case.standard_name
    }


def test_cf_attributes_for_round_trips_with_cfcontext(
    ureg: pint.UnitRegistry,
) -> None:
    with CFContext(standard_name="sound_pressure_level_in_air"):
        q = ureg.Quantity(74, "dB")

    assert cf_attributes_for(q) == {"standard_name": "sound_pressure_level_in_air"}


def test_cf_attributes_for_plain_decibel_is_empty(ureg: pint.UnitRegistry) -> None:
    assert cf_attributes_for(ureg.Unit("decibel")) == {}
    assert cf_attributes_for(ureg.Unit("meter")) == {}


# =============================================================================
# cf_extensions=False: dB/decibel isn't defined at all, so standard_name
# resolution can't apply either (see CFContext's docstring)
# =============================================================================


@pytest.fixture(scope="module")
def strict_ureg() -> pint.UnitRegistry:
    return cf_unitregistry(cf_extensions=False)


@pytest.mark.parametrize("case", REFERENCE_LEVELS, ids=lambda c: c.standard_name)
def test_standard_name_raises_without_cf_extensions(
    strict_ureg: pint.UnitRegistry, case: ReferenceLevel
) -> None:
    with pytest.raises(pint.errors.UndefinedUnitError):
        with CFContext(standard_name=case.standard_name):
            strict_ureg.Quantity(74, "dB")
