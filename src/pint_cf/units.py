import warnings
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
_CF_EXTENSIONS_RESOURCE = "cf-extensions.txt"

# Dimensionless vertical coordinate placeholders CF keeps only for COARDS
# backwards compatibility and calls "deprecated by this standard" outright
# (CF conventions, units section) - see resources/registry/cf-extensions.txt.
_DEPRECATED_CF_UNITS = {
    "level",
    "levels",
    "sigma_level",
    "sigma_levels",
    "layer",
    "layers",
}


def _warn_if_deprecated_cf_unit(unit_string: str) -> str:
    """Preprocessor: warn on a bare deprecated CF vertical-coordinate unit.

    A no-op transform (returns its input unchanged) purely for the
    DeprecationWarning side effect - these units are only ever used bare
    (e.g. ``units = "level"``), never combined with anything else.
    """
    if unit_string.strip() in _DEPRECATED_CF_UNITS:
        warnings.warn(
            f"{unit_string.strip()!r} is a dimensionless vertical "
            "coordinate placeholder kept only for COARDS backwards "
            "compatibility - CF conventions (units section) call it "
            "deprecated outright in favor of a proper vertical "
            "coordinate variable.",
            DeprecationWarning,
            stacklevel=2,
        )
    return unit_string


class _NoCache(dict):
    """A dict that never stores anything - every lookup is a cache miss.

    Used to disable pint's `_cache.parse_unit`, which memoizes a parsed unit
    result keyed on the RAW string, before preprocessors run. Left enabled,
    a later call with the same raw string but a different (or no) active
    CFContext would silently return the stale cached result instead of
    re-running cf_string_to_pint - this makes CFContext work transparently
    with plain pint calls like ureg.Quantity(value, units), instead of
    requiring a pint-cf-specific replacement for them.
    """

    def __setitem__(self, key: Any, value: Any) -> None:
        pass


class CFFormatter(DefaultFormatter):
    """Formatter for CF-compliant unit strings.

    Registered under the ``"cf"`` format spec by `cf_unitregistry`;
    not meant to be instantiated directly.
    """

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


def cf_unitregistry(*, cf_extensions: bool = True) -> pint.UnitRegistry:
    """Create a CF-ready pint UnitRegistry.

    Configured with the UDUNITS-2 registry, the `cf_string_to_pint`
    preprocessor, and the ``"cf"`` formatter.

    Parameters
    ----------
    cf_extensions : bool, optional
        By default (``True``), the registry also includes CF units
        that UDUNITS-2 itself doesn't define - ``level``,
        ``sigma_level``, ``layer`` (dimensionless vertical-coordinate
        placeholders, deprecated - parsing one raises
        ``DeprecationWarning``), ``practical_salinity_unit``/``psu``,
        ``decibel``/``dB``, ``bel``, and reassigning the ``Sv`` symbol
        from ``sievert`` to ``sverdrup``. Sourced from `cfunits`
        (https://github.com/NCAS-CMS/cfunits), see
        ``resources/registry/cf-extensions.txt``. Pass ``False`` to
        get a registry that matches plain UDUNITS-2 instead, without
        any of these additions.

    Returns
    -------
    pint.UnitRegistry
        A registry ready to parse UDUNITS-2/CF unit strings and to
        format results back with ``format(q, "cf")`` /
        ``format(q, "~cf")``.

    """
    preprocessors = [cf_string_to_pint]
    if cf_extensions:
        preprocessors.insert(0, _warn_if_deprecated_cf_unit)

    with resources.path("pint_cf.resources.registry", "udunits2.txt") as filename:
        ureg = pint.UnitRegistry(
            filename=str(filename),
            autoconvert_offset_to_baseunit=True,
            preprocessors=preprocessors,
        )

    if cf_extensions:
        with resources.path(
            "pint_cf.resources.registry", _CF_EXTENSIONS_RESOURCE
        ) as cf_extensions_filename:
            ureg.load_definitions(str(cf_extensions_filename))

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

    # See _NoCache: without this, ureg.Quantity(value, units) (or ureg(units))
    # would only pick up an active CFContext the FIRST time a given raw
    # string is parsed - later calls with the same string but a different
    # (or no) context would silently get the first call's stale result.
    #
    # Measured cost: none, in both a mixed-string workload and a
    # same-string-repeated-5000-times worst case (~40-60 us/call either way,
    # within noise, disabled sometimes even marginally faster). This cache is
    # keyed on the raw string BEFORE preprocessors run, but written back with
    # the string AFTER preprocessors run (registry.py:_parse_units_as_container)
    # - since cf_string_to_pint almost always changes the string (e.g.
    # "degree_C" -> "degree_Celsius"), the read and write keys rarely match
    # in the first place, so this cache was already close to a no-op for any
    # registry using a non-trivial preprocessor like ours.
    ureg._cache.parse_unit = _NoCache()

    return ureg
