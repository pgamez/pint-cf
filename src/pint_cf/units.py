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
            # as_ratio=False makes pint.formatter() always show negative
            # exponents instead of a ratio, so division_fmt is never consulted;
            # kept only because pint.formatter() requires the argument.
            division_fmt = ""
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


def _register_cf_formatter(ureg: pint.UnitRegistry) -> None:
    """Register the CF formatter in both registry-local and Pint-global maps.

    Both are required: CFFormatter only overrides format_unit, so it inherits
    DefaultFormatter.format_quantity, which calls split_format() to separate a
    combined spec (e.g. ".2f~cf") into magnitude/unit parts. split_format()
    only recognizes flags present in the global REGISTERED_FORMATTERS, not in
    ureg.formatter._formatters - this mirrors what pint's own public
    pint.register_unit_format() does internally, not a private-API workaround.
    """
    formatter = CFFormatter(ureg)
    ureg.formatter._formatters[_CF_FORMATTER_NAME] = formatter
    REGISTERED_FORMATTERS[_CF_FORMATTER_NAME] = formatter


def cf_unitregistry() -> pint.UnitRegistry:
    """Create a CF-ready UnitRegistry with parser and formatter configured."""
    with resources.path("pint_cf.resources.registry", "udunits2.txt") as filename:
        ureg = pint.UnitRegistry(
            filename=str(filename),
            autoconvert_offset_to_baseunit=True,
            preprocessors=[cf_string_to_pint],
        )

    # Deliberately NOT setting ureg.formatter.default_format = "cf": pint only
    # applies default_format when the format spec is completely empty
    # (str(q), format(q)). For ANY other explicit spec (even "{:.2f}"), pint's
    # formatter dispatch (delegates/formatter/full.py: get_formatter) picks a
    # formatter by checking if a known flag is a literal substring of that
    # spec - it doesn't consult default_format at all - so it silently falls
    # back to the plain (non-CF) formatter and only issues a
    # DeprecationWarning. Requiring an explicit "cf"/"~cf" spec is more
    # predictable than a default that silently stops applying. Verified
    # against pint 0.25.2; may be worth revisiting if pint fixes this.

    # Deactivate Pint's native pluralization, since UDUNITS2 already
    # defines plural forms for units
    ureg._suffixes = {"": ""}
    _register_cf_formatter(ureg)
    return ureg
