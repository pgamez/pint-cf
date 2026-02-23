from importlib import resources

import pint
from packaging.version import Version

from .parser import udunits_to_pint


@pint.register_unit_format("cf")
def short_formatter(unit, registry, **options):
    """Return a CF-compliant unit string from a `pint` unit.

    Parameters
    ----------
    unit : pint.UnitContainer
        Input unit.
    registry : pint.UnitRegistry
        The associated registry
    **options
        Additional options (may be ignored)

    Returns
    -------
    out : str
        Units following CF-Convention, using symbols.
    """
    # pint 0.24.1 gives {"dimensionless": 1} for non-shortened dimensionless units
    # CF uses "1" to denote fractions and dimensionless quantities
    if unit == {"dimensionless": 1} or not unit:
        return "1"

    # If u is a name, get its symbol (same as pint's "~" pre-formatter)
    # otherwise, assume a symbol (pint should have already raised on invalid units before this)
    unit = pint.util.UnitsContainer(
        {
            registry._get_symbol(u) if u in registry._units else u: exp
            for u, exp in unit.items()
        }
    )

    is_short = True

    # Change in formatter signature in pint 0.24
    if Version(pint.__version__) < Version("0.24"):
        args = (unit.items(),)
    else:
        # Numerators splitted from denominators
        args = (
            ((u, e) for u, e in unit.items() if e >= 0),
            ((u, e) for u, e in unit.items() if e < 0),
        )

    if is_short:
        out = pint.formatter(
            *args, as_ratio=True, product_fmt=".", power_fmt="{}{}", division_fmt="/"
        )
    else:
        out = pint.formatter(
            *args,
            as_ratio=True,
            product_fmt=" ",
            power_fmt="{}^{}",
            division_fmt=" per ",
        )
    # out = pint.formatter(*args, as_ratio=False, product_fmt=".", power_fmt="{}^{}")
    # To avoid potentiel unicode problems in netCDF. In both cases, this unit is not recognized by udunits
    # return out.replace("Δ°", "delta_deg")
    return out.replace("Δ", "").replace("delta_", "")  # XXX: falta el replace long


def cf_unitregistry() -> pint.UnitRegistry:
    """Factory function to create a CFUnitRegistry instance."""
    with resources.path("pint_cf.resources.registry", "udunits2.txt") as fspath:
        ureg = pint.UnitRegistry(
            filename=str(fspath),
            autoconvert_offset_to_baseunit=True,
            preprocessors=[udunits_to_pint],
        )
    ureg.formatter.default_format = "cf"

    # Deactivate Pint's native pluralization, since UDUNITS2 already
    # defines plural forms for units
    ureg._suffixes = {"": ""}

    # set_application_registry(ureg)
    return ureg


if __name__ == "__main__":
    # Quick test cases
    ureg = cf_unitregistry()
    print("=== CF Unit Registry Test Cases ===\n")

    # Test 1: Registry creation
    print("✓ Registry created:", type(ureg).__name__)

    # Test 2: Dimensionless units
    print("\n--- Dimensionless Units ---")
    u = ureg.Unit("1")
    print(f"Unit('1') → {u:~cf}")

    # Test 3: Basic units with CF format
    print("\n--- Basic Units ---")
    for unit_str in ["meter", "kilometers", "kilogram", "second"]:
        u = ureg.Unit(unit_str)
        print(f"{unit_str:20s} → {u:~cf}")

    # Test 4: Compound units
    print("\n--- Compound Units ---")
    compound_units = ["m s-2", "W.m-2", "micrograms/m3", "meter^2 per s^2"]
    for unit_str in compound_units:
        u = ureg.Unit(unit_str)
        print(f"{unit_str:20s} → {u:~cf}")

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
        print(f"{unit_str:20s} → {u:~cf}")

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
            print(f"{unit_str:25s} → {u:~cf:15s} {status}")
        except Exception as e:
            status = (
                "✗ (failed as expected)"
                if not should_work
                else f"✗ ERROR: {type(e).__name__}"
            )
            print(f"{unit_str:25s} → {status}")

    print("\n✓ All test cases completed")
