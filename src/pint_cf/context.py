"""
CF variable attributes (e.g. units_metadata) going in and out of pint.

Going in: pint's preprocessors are plain `Callable[[str], str]` - they cannot
receive extra arguments, so there is no way to pass a CF attribute like
`units_metadata` to a preprocessor when pint calls it internally. `CFContext`
makes such attributes available to the temperature preprocessor built by
`_make_temperature_preprocessor` via a `ContextVar`, without changing pint's
own UnitRegistry/Unit/Quantity classes.

Going out: `cf_attributes_for` derives CF variable attributes (currently just
`units_metadata`) back from an already-computed Unit/Quantity, e.g. to write
out with a result.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import pint
from pint.facets.plain import PlainQuantity, PlainUnit
from pint.util import ParserHelper

_TEMPERATURE_MODES = {"on_scale", "difference", "unknown"}

_temperature_mode: ContextVar[str | None] = ContextVar(
    "_temperature_mode", default=None
)


def _parse_units_metadata(value: str) -> str:
    key, _, mode = value.partition(":")
    key, mode = key.strip(), mode.strip()

    if key != "temperature" or mode not in _TEMPERATURE_MODES:
        raise ValueError(
            f"Invalid units_metadata: {value!r}. Expected one of "
            "'temperature: on_scale', 'temperature: difference', "
            "'temperature: unknown' (CF conventions, section 3.1.2)."
        )

    return mode


@contextmanager
def CFContext(*, units_metadata: str | None = None) -> Iterator[None]:
    """Apply a CF ``units_metadata`` attribute while building a unit or quantity.

    A NetCDF/CF variable can carry a ``units_metadata`` attribute that
    disambiguates a temperature unit as either a point on a scale
    (``"temperature: on_scale"``, e.g. a measured temperature of 15
    degrees Celsius) or a difference between two temperatures
    (``"temperature: difference"``, e.g. a 5-degree warming). Plain
    pint has no way to know which one you mean from the unit string
    alone. Wrap the ``ureg.Quantity(...)``/``ureg.Unit(...)`` call
    that needs this distinction in a ``with CFContext(...):`` block,
    and it will resolve to the right pint unit (e.g.
    ``delta_degree_Celsius`` for a difference).

    Scope this tightly around a single unit/quantity construction:
    it must not wrap a loop over multiple variables that may carry
    different metadata, since the value set here is only reset on
    exiting the block.

    Parameters
    ----------
    units_metadata : str or None, optional
        A CF ``units_metadata`` attribute value, e.g.
        ``"temperature: difference"`` (`CF conventions, section 3.1.2,
        "Temperature units"
        <https://cfconventions.org/cf-conventions/cf-conventions.html#temperature-units>`_).
        ``None`` (the default) is a no-op.

    Yields
    ------
    None

    Raises
    ------
    ValueError
        If `units_metadata` is set but isn't one of the values CF
        defines for the ``temperature`` key.

    Examples
    --------
    >>> with CFContext(units_metadata="temperature: difference"):
    ...     q = ureg.Quantity(1, "degree_C")
    >>> q.units
    <Unit('delta_degree_Celsius')>

    """
    mode = _parse_units_metadata(units_metadata) if units_metadata is not None else None
    token = _temperature_mode.set(mode)
    try:
        yield
    finally:
        _temperature_mode.reset(token)


def _current_temperature_mode() -> str | None:
    """The temperature mode ('on_scale' | 'difference' | 'unknown') from the
    innermost active `CFContext`, or None if no context is active."""
    return _temperature_mode.get()


def _strip_enclosing_parens(pint_string: str) -> str:
    """Strip parentheses that wrap the *entire* string, one layer at a time
    - e.g. "((degree_C))" -> "degree_C", but "(m) * (s)" is left untouched,
    since its leading "(" closes before the string ends (it doesn't enclose
    the whole expression, just part of it).
    """
    while pint_string.startswith("(") and pint_string.endswith(")"):
        depth = 0
        for i, char in enumerate(pint_string):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    if i != len(pint_string) - 1:
                        return pint_string  # closes early - not fully enclosing
                    break
        pint_string = pint_string[1:-1]
    return pint_string


def _is_bare_unit(pint_string: str) -> bool:
    """True for a single unit at unity power - e.g. "degree_Celsius" or the
    (unusual but valid) "degree_Celsius ** 1" - as opposed to a compound
    expression: a product, a ratio, a non-unity power, an offset, or a
    logarithmic unit. Matches UDUNITS' own rule for when a temperature unit
    counts as a difference: "raised to any power other than unity, or
    multiplied or divided by any other unit" - unity power must still count
    as bare even though its pint string contains "**".

    Checks for the operator characters themselves rather than a specific
    spacing convention - unit names never contain "/", ";", or "*" (see the
    ID terminal in udunits2.lark), so their mere presence is unambiguous.
    "*" also appears as half of "**", so it's checked on the base only,
    after splitting off a trailing power.
    """
    if "/" in pint_string or ";" in pint_string:
        return False

    if "**" not in pint_string:
        return "*" not in pint_string

    base, exponent = pint_string.rsplit("**", 1)
    return "*" not in base and exponent.strip() in ("1", "+1")


def _is_offset_temperature_unit(registry: pint.UnitRegistry, name: str) -> bool:
    """True for a temperature unit with its own offset (e.g. degree_Celsius,
    fahrenheit) - the only units where on_scale and difference are different
    pint units. False for kelvin/degree_rankine (no offset, so on_scale and
    difference are the same unit), for an already-delta_ unit, for any
    non-temperature unit - including logarithmic ones like B, which pint
    also counts as non-multiplicative - and for an unknown name (left for
    pint itself to report).

    Same name resolution as pint's own `registry._is_multiplicative`
    (prefixes, plurals, aliases), minus its bare `assert` on an unknown
    name - an IndexError instead under `python -O`.

    Runs inside a preprocessor, so it must not call any registry method
    that takes a unit *string*: since pint 0.26, those (e.g.
    `get_dimensionality(str)`) apply the preprocessors themselves, which
    would recurse back into this one. `parse_unit_name` and
    `_get_dimensionality(UnitsContainer)` don't.
    """
    if name in registry._units:
        base_names = [name]
    else:
        base_names = [base for _, base, _ in registry.parse_unit_name(name)]

    return any(
        not registry._units[base].is_multiplicative
        and registry._get_dimensionality(registry.UnitsContainer({base: 1}))
        == "[temperature]"
        for base in base_names
    )


def _involves_offset_temperature(registry: pint.UnitRegistry, pint_string: str) -> bool:
    """True if any unit in `pint_string` (a cf_string_to_pint result) is an
    offset temperature unit - see `_is_offset_temperature_unit`."""
    return any(
        _is_offset_temperature_unit(registry, name)
        for name in ParserHelper.from_string(pint_string)
    )


def _make_temperature_preprocessor(
    registry: pint.UnitRegistry,
) -> Callable[[str], str]:
    """Build the pint preprocessor that applies the active CFContext's
    temperature mode, bound to `registry`.

    Runs right after `cf_string_to_pint` in the preprocessor chain, which
    keeps that one a pure UDUNITS-to-pint syntax translation. This step is
    the only one that needs the registry - to tell an offset temperature
    unit (degree_C) from one without an offset (K), which a unit string
    alone can't - so it can only be built once the registry exists, and is
    appended to `registry.preprocessors` afterwards by `cf_unitregistry`.
    """

    def apply_temperature_mode(pint_string: str) -> str:
        return _apply_temperature_mode(pint_string, registry)

    return apply_temperature_mode


def _apply_temperature_mode(result: str, registry: pint.UnitRegistry) -> str:
    """Apply the active CFContext's temperature mode to a unit already
    converted by cf_string_to_pint.

    Only units involving an offset temperature unit (degree_C, degree_F)
    are touched: for anything else - kelvin, a non-temperature unit, or a
    compound of those - on_scale and difference are the same pint unit, so
    the mode has nothing to change. CF forbids units_metadata on a
    non-temperature unit, but this is a reader, not a validator: such
    metadata is ignored rather than rejected.

    Absent/"unknown" needs no handling here: pint's own default
    `as_delta=True` behavior already applies UDUNITS' own heuristic (a
    non-multiplicative unit gets its delta_ counterpart whenever it's raised
    to a power other than unity, or combined with another unit).
    """
    mode = _current_temperature_mode()
    if mode not in ("difference", "on_scale"):
        return result

    # A single unit stays "bare" regardless of enclosing parens (e.g.
    # "(degree_C)", "((degree_C))") - strip them first, since the parens are
    # otherwise redundant once delta_ is prefixed, and prefixing "delta_"
    # onto the unstripped string would produce invalid syntax like
    # "delta_(degree_C)".
    body = _strip_enclosing_parens(result)

    # Also makes this idempotent - pint can re-apply its preprocessors to an
    # already-processed string, and an already-prefixed delta_ unit has no
    # offset of its own.
    if not _involves_offset_temperature(registry, body):
        return result

    is_bare = _is_bare_unit(body)

    if mode == "difference" and is_bare:
        return f"delta_{body}"

    if mode == "on_scale" and not is_bare:
        # Valid CF (section 3.1.2), but there is no safe pint
        # representation for it. pint reads an offset unit inside a
        # compound unit as its delta_ counterpart (which would contradict
        # the metadata), and the only way around that -
        # parse_units(..., as_delta=False) - gives a unit that pint (0.25-0.26)
        # converts silently wrong under autoconvert_offset_to_baseunit=True
        # (e.g. 10 kg degC m-2 -> 10 g degC m-2, not 10000). So refuse it
        # and point to the route CF itself describes: the separate values.
        # Multiplying those quantities is correct - pint converts the
        # on-scale temperature to kelvin first.
        raise ValueError(
            "units_metadata='temperature: on_scale' on a compound unit "
            f"({result!r}) can't be represented safely in pint: an offset "
            "temperature unit (degC, degF) inside a compound unit is either "
            "read as a difference or, forced on-scale, converted "
            "incorrectly. As CF (section 3.1.2) notes, such values can only "
            "be converted if the on-scale temperature and the other factors "
            "are known separately: if they are, build each as its own "
            "quantity and multiply them, e.g. "
            "ureg.Quantity(t, 'degC') * ureg.Quantity(x, 'kg m-2')."
        )

    return result


def _component_temperature_mode(registry: pint.UnitRegistry, cname: str) -> str:
    is_delta = cname.startswith("delta_")
    base_name = cname.removeprefix("delta_") if is_delta else cname

    if registry._is_multiplicative(base_name):
        # No offset at all (e.g. kelvin, degree_rankine) - on_scale and
        # difference are numerically identical and can't be told apart.
        return "unknown"

    return "difference" if is_delta else "on_scale"


def cf_attributes_for(unit: PlainUnit | PlainQuantity) -> dict[str, str]:
    """Derive CF variable attributes from a pint Unit or Quantity.

    The reverse of what `CFContext` does going in: for writing a
    result back to a NetCDF variable, e.g. via
    ``var.setncatts(...)`` or ``ds[name].attrs.update(...)``.

    Currently only ever produces a ``units_metadata`` entry, and
    only for a temperature unit - CF's own rule is that this
    attribute must be absent unless the unit involves temperature,
    so a non-temperature unit (or one without a genuine
    on_scale/difference distinction to report) yields an empty dict
    rather than a key with a null-ish value.

    Only reliable for units with a genuine on_scale/difference
    distinction (Celsius, Fahrenheit - units with their own offset,
    which is why pint gives them a ``delta_`` counterpart at all).
    For Kelvin/Rankine (no offset, so no ``delta_`` variant exists),
    on_scale and difference are numerically identical and
    structurally indistinguishable from the unit alone - this
    reports ``"temperature: unknown"`` for those rather than
    guessing; if that distinction matters, the caller must track it
    through their own computation instead of recovering it from the
    resulting unit.

    It reports how pint interprets the unit, not the metadata the
    data was read with. A pint unit can't carry "unknown": with
    ``units_metadata="temperature: unknown"``, or with no
    ``units_metadata`` at all (which CF says readers must treat as
    unknown), pint falls back on the UDUNITS rule - a bare offset
    unit (``degC``) is read as on_scale, and a compound one
    (``degC/s``, ``degC2``) as a difference - and this function
    then reports that guess as ``"temperature: on_scale"`` /
    ``"temperature: difference"``. CF only cites that rule as
    guidance, not as a convention. So if the input's
    ``units_metadata`` was unknown or absent, writing this result
    back out would state something the original data didn't:
    keep the original attribute instead, unless your computation
    itself settled the question (e.g. subtracting two on-scale
    temperatures, which pint correctly turns into a difference).

    Parameters
    ----------
    unit : pint.Unit or pint.Quantity
        The unit (or quantity, from which `.units` is used) to
        derive CF attributes from.

    Returns
    -------
    dict of str to str
        ``{"units_metadata": ...}`` if `unit` involves temperature,
        otherwise ``{}``.

    Examples
    --------
    >>> cf_attributes_for(ureg.Unit("delta_degree_Celsius"))
    {'units_metadata': 'temperature: difference'}
    >>> cf_attributes_for(ureg.Unit("meter"))
    {}

    """
    unit = getattr(unit, "units", unit)
    registry = unit._REGISTRY

    temperature_components = [
        name
        for name in unit._units
        if registry.get_dimensionality(name) == "[temperature]"
    ]

    if not temperature_components:
        return {}

    modes = {
        _component_temperature_mode(registry, name) for name in temperature_components
    }

    if "difference" in modes:
        mode = "difference"
    elif modes == {"on_scale"}:
        mode = "on_scale"
    else:
        mode = "unknown"

    return {"units_metadata": f"temperature: {mode}"}
