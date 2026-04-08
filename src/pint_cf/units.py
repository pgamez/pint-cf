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

from .parser import cf_string_to_pint

_CF_FORMATTER_NAME = "cf"


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


def _register_cf_formatter(ureg: pint.UnitRegistry) -> pint.UnitRegistry:
    """Register the CF formatter in both registry-local and Pint-global maps."""
    formatter = CFFormatter(ureg)
    ureg.formatter._formatters[_CF_FORMATTER_NAME] = formatter
    REGISTERED_FORMATTERS[_CF_FORMATTER_NAME] = formatter
    return ureg


def cf_unitregistry() -> pint.UnitRegistry:
    """Create a CF-ready UnitRegistry with parser and formatter configured."""
    with resources.path("pint_cf.resources.registry", "udunits2.txt") as filename:
        ureg = pint.UnitRegistry(
            filename=str(filename),
            autoconvert_offset_to_baseunit=True,
            preprocessors=[cf_string_to_pint],
        )

    # ureg.formatter.default_format = "cf"

    # Deactivate Pint's native pluralization, since UDUNITS2 already
    # defines plural forms for units
    ureg._suffixes = {"": ""}
    return _register_cf_formatter(ureg)


def cf_set_application_registry() -> None:
    """Create and set the CF registry as the Pint application registry."""
    ureg = cf_unitregistry()
    pint.set_application_registry(ureg)
