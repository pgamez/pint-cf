"""
CF variable attributes (e.g. units_metadata, standard_name) going in and out
of pint.

Going in: pint's preprocessors are plain `Callable[[str], str]` - they cannot
receive extra arguments, so there is no way to pass a CF attribute like
`units_metadata` or `standard_name` directly to `cf_string_to_pint` when
pint calls it internally. `CFContext` makes such attributes available to it
via a `ContextVar`, without changing pint's own UnitRegistry/Unit/Quantity
classes.

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

# CF standard names whose canonical unit is dB, mapped to the pre-registered
# pint unit (see cf-extensions.txt) that carries their physical reference
# level and dimension. The pint side is leading-underscore: it's pint-cf's
# own invention (CF only defines the standard_name, not a unit for it), so
# the underscore marks it as a private implementation detail, never meant to
# be typed directly in a units string - CFFormatter maps it back to
# dB/decibel when formatting a result (units.py). Any other standard_name
# (or none) leaves a bare dB/decibel string as the plain dimensionless ratio
# unit, unchanged.
_DB_REFERENCE_UNITS = {
    "sound_intensity_level_in_air": "_dB_sound_intensity_level_in_air",
    "sound_intensity_level_in_water": "_dB_sound_intensity_level_in_water",
    "sound_pressure_level_in_air": "_dB_sound_pressure_level_in_air",
    "sound_pressure_level_in_water": "_dB_sound_pressure_level_in_water",
}
_DB_REFERENCE_UNIT_NAMES = frozenset(_DB_REFERENCE_UNITS.values())
_STANDARD_NAME_BY_DB_REFERENCE_UNIT = {
    unit_name: standard_name for standard_name, unit_name in _DB_REFERENCE_UNITS.items()
}

# Bare spellings of the plain dimensionless decibel unit (cf-extensions.txt)
# that a recognized standard_name may override. Deliberately excludes `bel`:
# CF's standard name table only ever pairs these standard names with dB.
_DB_BARE_UNIT_NAMES = frozenset({"decibel", "dB", "decibels"})

_standard_name: ContextVar[str | None] = ContextVar("_standard_name", default=None)


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
def CFContext(
    *, units_metadata: str | None = None, standard_name: str | None = None
) -> Iterator[None]:
    """Apply CF variable attributes while building a unit or quantity.

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

    Similarly, a decibel value's physical reference level isn't carried
    by the unit string (``"dB"``) at all - CF's FAQ says it "is specified
    in the standard names that use this canonical unit". Passing the
    variable's ``standard_name`` resolves a bare ``dB``/``decibel`` to a
    pint unit carrying that reference level (e.g. 2e-5 Pa for
    ``sound_pressure_level_in_air``), for one of the four CF standard
    names that use dB as their canonical unit. Any other standard_name
    (or none) leaves ``dB``/``decibel`` as the plain dimensionless ratio
    unit `cfunits`/`cf-units` also use.

    This decibel resolution needs the ``dB``/``decibel`` unit itself,
    which only exists with `cf_unitregistry`'s ``cf_extensions=True``
    (the default) - with ``cf_extensions=False``, a recognized
    standard_name raises ``UndefinedUnitError`` instead, same as plain
    ``dB`` does in that registry.

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
    standard_name : str or None, optional
        A CF ``standard_name`` attribute value. Only meaningful for a
        bare ``dB``/``decibel`` unit and one of the four CF standard
        names whose canonical unit is dB
        (``sound_intensity_level_in_air``,
        ``sound_intensity_level_in_water``,
        ``sound_pressure_level_in_air``,
        ``sound_pressure_level_in_water``) - any other value (or
        ``None``, the default) is a no-op.

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

    >>> with CFContext(standard_name="sound_pressure_level_in_air"):
    ...     q = ureg.Quantity(74, "dB")
    >>> q.to("pascal")
    <Quantity(0.1002374..., 'pascal')>

    """
    mode = _parse_units_metadata(units_metadata) if units_metadata is not None else None
    temperature_token = _temperature_mode.set(mode)
    standard_name_token = _standard_name.set(standard_name)
    try:
        yield
    finally:
        _temperature_mode.reset(temperature_token)
        _standard_name.reset(standard_name_token)


def _current_temperature_mode() -> str | None:
    """The temperature mode ('on_scale' | 'difference' | 'unknown') from the
    innermost active `CFContext`, or None if no context is active."""
    return _temperature_mode.get()


def _current_standard_name() -> str | None:
    """The ``standard_name`` from the innermost active `CFContext`, or None
    if no context is active."""
    return _standard_name.get()


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


def _apply_standard_name_reference(result: str) -> str:
    """Resolve a bare dB/decibel unit to its standard_name-specific physical
    reference level, under an active CFContext(standard_name=...).

    CF's own FAQ says the reference level a decibel value is relative to
    "is specified in the standard names that use this canonical unit" -
    with no active context (or any standard_name other than one of the
    four recognized ones), a dB/decibel string is left exactly as before:
    the plain dimensionless ratio unit `cfunits`/`cf-units` also use.
    Already-compound strings (e.g. an explicit UDUNITS `lg(re 1 uPa)`
    reference, or "dB / s") are left untouched too - they either already
    carry their own reference or don't represent a plain decibel value at
    all.
    """
    standard_name = _current_standard_name()
    if standard_name not in _DB_REFERENCE_UNITS:
        return result

    if _strip_enclosing_parens(result) not in _DB_BARE_UNIT_NAMES:
        return result

    return _DB_REFERENCE_UNITS[standard_name]


def _component_temperature_mode(registry, cname: str) -> str:
    is_delta = cname.startswith("delta_")
    base_name = cname.removeprefix("delta_") if is_delta else cname

    if registry._is_multiplicative(base_name):
        # No offset at all (e.g. kelvin, degree_rankine) - on_scale and
        # difference are numerically identical and can't be told apart.
        return "unknown"

    return "difference" if is_delta else "on_scale"


def _units_metadata_attribute(unit: PlainUnit, registry) -> dict[str, str]:
    """The ``units_metadata`` entry of `cf_attributes_for`, or `{}` if
    `unit` doesn't involve temperature at all."""
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


def _standard_name_attribute(unit: PlainUnit) -> dict[str, str]:
    """The ``standard_name`` entry of `cf_attributes_for`, or `{}` if
    `unit` isn't (exactly) one of the standard_name-resolved dB units.

    Unlike temperature's on_scale/difference, this is an exact 1:1
    mapping - each resolved unit maps back to exactly one standard_name
    (see `_apply_standard_name_reference`) - so no ambiguity to resolve,
    and no case analogous to Kelvin/Rankine's "unknown".
    """
    db_reference_components = [
        name for name in unit._units if name in _DB_REFERENCE_UNIT_NAMES
    ]

    if len(db_reference_components) != 1:
        # Never combined with anything else in practice (there's no
        # sensible "sound_pressure_level_in_air per second"), but a
        # combination - or none at all - can't be reported unambiguously.
        return {}

    (unit_name,) = db_reference_components
    return {"standard_name": _STANDARD_NAME_BY_DB_REFERENCE_UNIT[unit_name]}


def cf_attributes_for(unit: PlainUnit | PlainQuantity) -> dict[str, str]:
    """Derive CF variable attributes from a pint Unit or Quantity.

    The reverse of what `CFContext` does going in: for writing a
    result back to a NetCDF variable, e.g. via
    ``var.setncatts(...)`` or ``ds[name].attrs.update(...)``.

    Produces up to two entries, each independent of the other:

    - ``units_metadata``, only for a temperature unit - CF's own rule
      is that this attribute must be absent unless the unit involves
      temperature, so a non-temperature unit (or one without a
      genuine on_scale/difference distinction to report) contributes
      nothing rather than a key with a null-ish value.

      Only reliable for units with a genuine on_scale/difference
      distinction (Celsius, Fahrenheit - units with their own offset,
      which is why pint gives them a ``delta_`` counterpart at all).
      For Kelvin/Rankine (no offset, so no ``delta_`` variant
      exists), on_scale and difference are numerically identical and
      structurally indistinguishable from the unit alone - this
      reports ``"temperature: unknown"`` for those rather than
      guessing; if that distinction matters, the caller must track
      it through their own computation instead of recovering it from
      the resulting unit.

    - ``standard_name``, only if `unit` is one that a
      `CFContext(standard_name=...)` call resolved a decibel value to
      (see `CFContext`) - each one maps back to exactly one
      standard_name, so this is a direct, unambiguous lookup, not a
      guess.

    Parameters
    ----------
    unit : pint.Unit or pint.Quantity
        The unit (or quantity, from which `.units` is used) to
        derive CF attributes from.

    Returns
    -------
    dict of str to str
        Any of ``{"units_metadata": ...}``, ``{"standard_name": ...}``,
        both, or ``{}`` if neither applies.

    Examples
    --------
    >>> cf_attributes_for(ureg.Unit("delta_degree_Celsius"))
    {'units_metadata': 'temperature: difference'}
    >>> with CFContext(standard_name="sound_pressure_level_in_air"):
    ...     q = ureg.Quantity(74, "dB")
    >>> cf_attributes_for(q)
    {'standard_name': 'sound_pressure_level_in_air'}
    >>> cf_attributes_for(ureg.Unit("meter"))
    {}

    """
    if isinstance(unit, PlainQuantity):
        unit = unit.units
    registry = unit._REGISTRY

    return {
        **_units_metadata_attribute(unit, registry),
        **_standard_name_attribute(unit),
    }
