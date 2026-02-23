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
    with resources.path("pint_cf.resources.txt", "udunits2.txt") as fspath:
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
    ureg = cf_unitregistry()
    print(ureg)

    from pint import Quantity

    c = Quantity(10, ureg.degree_Celsius)
    print(c)
    print(c.to("kelvin"))

    a = ureg.arc_second
    print(f"{a:~cf}")

    print(ureg.Unit("1"))
    print(ureg.Unit("meter"))
    print(ureg.Unit("kilometers"))
    print(f"{ureg.Unit('kilometers'):~cf}")
    print(ureg.Unit("ug"))
    print(ureg.Unit("micrograms/m3"))
    print(ureg.Unit("degree_Celsius"))
    print(ureg.Unit("degrees_Celsius"))
    print(ureg.Unit("W.m-2"))
    # print(ureg.Unit("degKs"))
    print(ureg.Unit("m s-2"))
    print(f"{ureg.Unit('m s-2'):~cf}")
    print(ureg.Unit("meter per second"))
    print(f"{ureg.Unit('meter^2 s-2')}")
    print(f"{ureg.Unit('degree_west'):~cf}")
    print(ureg.Unit("'"))
