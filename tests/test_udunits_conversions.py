"""
Without CFContext, pint-cf must convert like UDUNITS-2.

The expected values in tests/data/udunits_conversions.tsv were computed by
the UDUNITS-2 C library itself, through cf_units, by
tools/write_udunits_conversions.py - so these tests don't depend on
cf_units. Mostly temperatures: CF 1.13 section 3.1.2 says to read a
variable without units_metadata as "temperature: unknown", and for that
case pint-cf follows the UDUNITS assumption CF quotes (bare unit
on-scale, compound unit a difference).

Checked against the registry without the CF extensions, which differ from
UDUNITS on purpose (psu, Sv as sverdrup) - see test_cf_extensions.py.
"""

from pathlib import Path

import pint
import pytest

from pint_cf import CFContext

NOT_CONVERTIBLE = "not convertible"

_CONVERSIONS = [
    line.split("\t")
    for line in (Path(__file__).parent / "data" / "udunits_conversions.tsv")
    .read_text(encoding="utf-8")
    .splitlines()
    if line and not line.startswith("#")
]

CONVERTIBLE = [
    pytest.param(float(value), units, target, float(expected), id=f"{units}->{target}")
    for value, units, target, expected in _CONVERSIONS
    if expected != NOT_CONVERTIBLE
]
NOT_CONVERTIBLE_PAIRS = [
    pytest.param(units, target, id=f"{units}->{target}")
    for _, units, target, expected in _CONVERSIONS
    if expected == NOT_CONVERTIBLE
]

# No CFContext at all, and the two ways CF spells "unknown".
NO_METADATA = pytest.mark.parametrize(
    "units_metadata", [None, "temperature: unknown"], ids=["absent", "unknown"]
)


@pytest.mark.parametrize("value, units, target, expected", CONVERTIBLE)
def test_converts_like_udunits(
    strict_ureg: pint.UnitRegistry,
    value: float,
    units: str,
    target: str,
    expected: float,
) -> None:
    converted = strict_ureg.Quantity(value, units).to(target)
    assert converted.magnitude == pytest.approx(expected, rel=1e-12, abs=1e-12)


@NO_METADATA
@pytest.mark.parametrize("value, units, target, expected", CONVERTIBLE)
def test_converts_like_udunits_with_units_metadata_unknown(
    strict_ureg: pint.UnitRegistry,
    units_metadata: str | None,
    value: float,
    units: str,
    target: str,
    expected: float,
) -> None:
    with CFContext(units_metadata=units_metadata):
        converted = strict_ureg.Quantity(value, units).to(target)
    assert converted.magnitude == pytest.approx(expected, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("units, target", NOT_CONVERTIBLE_PAIRS)
def test_refuses_what_udunits_refuses(
    strict_ureg: pint.UnitRegistry, units: str, target: str
) -> None:
    with pytest.raises((pint.DimensionalityError, pint.UndefinedUnitError)):
        strict_ureg.Quantity(1, units).to(target)
