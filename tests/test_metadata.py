"""Tests for the UnitsMetadata class."""

import pytest

from pint_cf.metadata import UnitsMetadata

# Test cases for UnitsMetadata.from_unit with temperature units
TEST_CASES_FROM_UNIT_TEMP = [
    ("degree_Celsius", "temperature: on_scale", "degree_Celsius"),
    ("degree_Celsius", "temperature: difference", "delta_degree_Celsius"),
    ("degree_Celsius", "temperature: unknown", "degree_Celsius"),
    ("degree_Celsius", "", "degree_Celsius"),
    # ("K", "temperature: on_scale"),
    # ("°C", "temperature: on_scale"),
    # ("°F", "temperature: on_scale"),
    # ("degC", "temperature: on_scale"),
    # ("degF", "temperature: on_scale"),
    # ("delta_degC", "temperature: difference"),
    # ("delta_degF", "temperature: difference"),
]

TEST_CASES_SERIALIZATION = [
    ("degree_Celsius", "temperature: on_scale", "degree_Celsius"),
    ("degree_Celsius", "temperature: difference", "delta_degree_Celsius"),
]


@pytest.mark.parametrize(
    "units, units_metadata, expected_units", TEST_CASES_FROM_UNIT_TEMP
)
def test_context_manager(ureg, units, units_metadata, expected_units):
    # Inside context manager
    with UnitsMetadata(units_metadata):
        u = ureg(units)

    assert u.units == ureg.parse_units(expected_units)


@pytest.mark.parametrize(
    "units, units_metadata, expected_units", TEST_CASES_SERIALIZATION
)
def test_serialization(ureg, units, units_metadata, expected_units):
    q = ureg(expected_units)
    metadata1 = UnitsMetadata.from_quantity(q)
    metadata2 = UnitsMetadata.from_unit(q.units)

    assert metadata1.to_str() == units_metadata
    assert metadata2.to_str() == units_metadata

    assert metadata1.to_str() == units_metadata
    assert f"{q:cf}" == f"{ureg(units):cf}"
