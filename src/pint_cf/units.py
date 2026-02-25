from collections.abc import Iterable
from importlib import resources
from typing import Any, Unpack

import pint
from pint.delegates.formatter._compound_unit_helpers import (
    BabelKwds,
    SortFunc,
    prepare_compount_unit,
)
from pint.delegates.formatter._spec_helpers import REGISTERED_FORMATTERS
from pint.delegates.formatter.plain import DefaultFormatter
from pint.facets.plain import PlainUnit

from .parser import udunits_to_pint


def cf_unitregistry() -> pint.UnitRegistry:
    with resources.path("pint_cf.resources.registry", "udunits2.txt") as fspath:
        ureg = pint.UnitRegistry(
            filename=str(fspath),
            autoconvert_offset_to_baseunit=True,
            preprocessors=[udunits_to_pint],
        )

    # ureg.formatter.default_format = "cf"

    # Deactivate Pint's native pluralization, since UDUNITS2 already
    # defines plural forms for units
    ureg._suffixes = {"": ""}
    return ureg


class CFFormatter(DefaultFormatter):
    """Formatter for CF-compliant unit strings."""

    def format_unit(
        self,
        unit: PlainUnit | Iterable[tuple[str, Any]],
        uspec: str = "",
        sort_func: SortFunc | None = None,
        **babel_kwds: Unpack[BabelKwds],
    ) -> str:
        if "~" in uspec:
            as_ratio = True
            product_fmt = "."
            division_fmt = "/"
            power_fmt = "{}{}"
        else:
            as_ratio = False
            product_fmt = "-"
            division_fmt = " per "
            power_fmt = "{}^{}"

        numerator, denominator = prepare_compount_unit(
            unit,
            uspec,
            sort_func=sort_func,
            **babel_kwds,
            registry=self._registry,
        )

        return (
            pint.formatter(
                numerator,
                denominator,
                as_ratio=as_ratio,
                product_fmt=product_fmt,
                division_fmt=division_fmt,
                power_fmt=power_fmt,
            )
            .replace("Δ", "")
            .replace("delta_", "")
            .replace("dimensionless", "")
        ) or "1"


def setup_cf_registry() -> None:
    """Set up the CF formatter as the default for pint."""
    ureg = cf_unitregistry()
    ureg.formatter._formatters["cf"] = CFFormatter(ureg)
    pint.set_application_registry(ureg)
    REGISTERED_FORMATTERS["cf"] = CFFormatter()


if __name__ == "__main__":
    # Quick test cases
    setup_cf_registry()
    ureg = pint.get_application_registry()

    print("=== CF Unit Registry Test Cases ===\n")

    # Test 1: Registry creation
    print("✓ Registry created:", type(ureg).__name__)

    # Test 2: Dimensionless units
    print("\n--- Dimensionless Units ---")
    u = ureg.Unit("1")
    print(f"Unit('1') → Long: {u:cf} -> Short: {u:~cf}")

    # Test 3: Basic units with CF format
    print("\n--- Basic Units ---")
    for unit_str in ["meter", "kilometers", "kilogram", "second"]:
        u = ureg.Unit(unit_str)
        print(f"{unit_str:20s} → Long: {u:cf} -> Short: {u:~cf}")

    # Test 4: Compound units
    print("\n--- Compound Units ---")
    compound_units = ["m s-2", "W.m-2", "micrograms/m3", "meter^2 per s^2"]
    for unit_str in compound_units:
        u = ureg.Unit(unit_str)
        print(f"{unit_str:20s} → Long: {u:cf} -> Short: {u:~cf}")

    # Test 5: Temperature units
    print("\n--- Temperature Units ---")
    from pint import Quantity

    c = Quantity(10, ureg.degree_Celsius)
    print(f"10 °C = {c.to('kelvin'):.2f}")
    print(f"degree_Celsius → {ureg.Unit('degree_Celsius'):~cf}")

    # Test 6: Angular units
    print("\n--- Angular Units ---")
    for unit_str in ["degree", "arc_second", "degree_west", "'"]:
        u = ureg.Unit(unit_str)
        print(f"{unit_str:20s} → Long: {u:cf} -> Short: {u:~cf}")

    # Test 7: Plural forms (valid and invalid)
    print("\n--- Plural Units ---")
    plural_tests = [
        ("meters", True),  # Valid plural
        ("degrees_Celsius", True),  # Valid plural in udunits
        ("kilometers", True),  # Valid plural
        (
            "degree_Celsiuss",
            False,
        ),  # Invalid: double 's' (pint accepts, udunits doesn't)
        ("seconds", True),  # Valid plural
    ]
    for unit_str, should_work in plural_tests:
        try:
            u = ureg.Unit(unit_str)
            status = "✓" if should_work else "✗ (expected to fail)"
            print(f"{unit_str:25s} → Long: {u:cf} -> Short: {u:~cf} {status}")
        except Exception as e:
            status = (
                "✗ (failed as expected)"
                if not should_work
                else f"✗ ERROR: {type(e).__name__}"
            )
            print(f"{unit_str:25s} → {status}")

    print("\n✓ All test cases completed")

    print(f"{ureg('1 degC'):~cf}")

    import numpy as np

    x = np.array([1.0, 2.0, 3.0])
    q = x * ureg.meter
    print(f"Quantity with array magnitude: {q:cf}")
    print(f"Quantity with array magnitude: {q[1]:~cf}")
