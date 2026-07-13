"""
CF variable attributes (e.g. units_metadata) going in and out of pint.

Going in: pint's preprocessors are plain `Callable[[str], str]` - they cannot
receive extra arguments, so there is no way to pass a CF attribute like
`units_metadata` directly to `cf_string_to_pint` when pint calls it
internally. `CFContext` makes such attributes available to it via a
`ContextVar`, without changing pint's own UnitRegistry/Unit/Quantity classes.

Going out: `cf_attributes_for` derives CF variable attributes (currently just
`units_metadata`) back from an already-computed Unit/Quantity, e.g. to write
out with a result.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from pint.facets.plain import PlainQuantity, PlainUnit

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
    """Make a CF variable attribute visible to `cf_string_to_pint`.

    Scope this tightly around a single unit/quantity construction:
    it must not wrap a loop over multiple variables that may carry
    different metadata, since the value set here is only reset on
    exiting the block.

    Parameters
    ----------
    units_metadata : str or None, optional
        A CF ``units_metadata`` attribute value, e.g.
        ``"temperature: difference"`` (CF conventions, section
        3.1.2). ``None`` (the default) is a no-op.

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


def _apply_temperature_mode(result: str) -> str:
    """Apply the active CFContext's temperature mode to a unit already
    converted by cf_string_to_pint.

    Absent/"unknown" needs no handling here: pint's own default
    `as_delta=True` behavior already applies UDUNITS' own heuristic (a
    non-multiplicative unit gets its delta_ counterpart whenever it's raised
    to a power other than unity, or combined with another unit).
    """
    mode = _current_temperature_mode()
    # A single unit stays "bare" regardless of enclosing parens (e.g.
    # "(degree_C)", "((degree_C))") - strip them first, since the parens are
    # otherwise redundant once delta_ is prefixed, and prefixing "delta_"
    # onto the unstripped string would produce invalid syntax like
    # "delta_(degree_C)".
    body = _strip_enclosing_parens(result)
    is_bare = _is_bare_unit(body)

    if mode == "difference" and is_bare:
        # cf_string_to_pint can run more than once on the same string within
        # one CFContext (e.g. pint re-applies its preprocessors internally) -
        # don't double up on an already-prefixed delta_ unit.
        if body.startswith("delta_"):
            return result
        return f"delta_{body}"

    if mode == "on_scale" and not is_bare:
        # pint decides delta_ substitution via the `as_delta` argument to
        # Unit()/Quantity(), which a preprocessor cannot influence - so this
        # override can't be honored transparently. Fail loudly rather than
        # silently returning a delta_ unit that contradicts the metadata.
        raise ValueError(
            "units_metadata='temperature: on_scale' cannot be applied to a "
            f"compound unit expression ({result!r}) through the automatic "
            "preprocessor pipeline. Call "
            "ureg.Quantity(value, units, as_delta=False) directly instead."
        )

    return result


def _component_temperature_mode(registry, cname: str) -> str:
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
    which is why pint gives them a delta_ counterpart at all). For
    Kelvin/Rankine (no offset, so no delta_ variant exists),
    on_scale and difference are numerically identical and
    structurally indistinguishable from the unit alone - this
    reports ``"temperature: unknown"`` for those rather than
    guessing; if that distinction matters, the caller must track it
    through their own computation instead of recovering it from the
    resulting unit.

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
