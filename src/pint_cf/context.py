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

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from tokenize import NAME

import pint
from pint.facets.plain import PlainQuantity, PlainUnit
from pint.pint_eval import tokenizer
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
def CFContext(*, units_metadata: str | None = None) -> Generator[None]:
    """Read temperatures with a CF ``units_metadata`` attribute.

    The ``units`` attribute alone doesn't say whether ``degC`` is a
    temperature or a temperature difference. CF adds
    ``units_metadata`` for that (CF 1.13, section 3.1.2). Inside the
    block, every temperature unit pint reads follows it, e.g.
    ``degC`` becomes ``delta_degree_Celsius`` for a difference.

    Rules:

    - One block, one variable. The metadata also applies to the
      target of ``.to()`` and to any unit read by code called from
      inside the block. Don't wrap several variables, or
      ``ds.pint.quantify()`` on a whole dataset, in one block.
    - Convert inside the block. Pint has no ``delta_`` unit for
      kelvin and Rankine, so a kelvin difference is just a kelvin.
      Outside the block, ``q.to("degF")`` reads ``"degF"`` as a
      temperature and gives a wrong number, without an error.

    Parameters
    ----------
    units_metadata : str or None, optional
        A CF ``units_metadata`` attribute value, e.g.
        ``"temperature: difference"`` (`CF conventions, section 3.1.2,
        "Temperature units"
        <https://cfconventions.org/cf-conventions/cf-conventions.html#temperature-units>`_).
        ``None`` (the default) means the variable has no
        ``units_metadata``, which CF reads as ``"temperature: unknown"``.
        It also clears the metadata of an outer block.

    Yields
    ------
    None

    Raises
    ------
    ValueError
        If `units_metadata` isn't a value CF defines for
        ``temperature``, or if it's ``"temperature: on_scale"`` and a
        unit read in the block is a compound one with Celsius or
        Fahrenheit (e.g. ``kg degC m-2``). CF says such a value can only
        be converted if the temperature and the other factors are known
        separately: multiply them as quantities instead.

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
    """Apply the active CFContext's temperature mode to a string already
    converted by cf_string_to_pint, by writing each offset temperature unit
    (degree_C, degree_F) that must be read as a difference as its delta_
    counterpart.

    - "temperature: difference": a difference, bare or compound - the
      metadata says so, whichever pint entry point reads the string.
    - "temperature: on_scale": bare stays on-scale; compound raises (see
      below).
    - "temperature: unknown" or absent: nothing to do - CF says the reader
      can't know, and that a correct conversion can't be guaranteed. pint
      is left to behave as documented: a unit string (Unit,
      Quantity(value, units), parse_units) follows its as_delta rule, the
      same assumption UDUNITS makes, which CF quotes as guidance only; a
      string evaluated as an expression (ureg(str), Quantity(str)) follows
      pint's arithmetic.

    Bare means the only unit, at unity power - pint's own as_delta rule. A
    leading number is a magnitude, not a unit: "5 degC" is bare, "2 degC/s"
    is compound.

    Units without an offset (kelvin, Rankine) and non-temperature units are
    never touched: on_scale and difference are the same pint unit for them.
    CF forbids units_metadata on a non-temperature unit, but this is a
    reader, not a validator: such metadata is ignored rather than rejected.
    """
    mode = _current_temperature_mode()
    if mode not in ("difference", "on_scale"):
        return result

    units = ParserHelper.from_string(result, registry.non_int_type)

    # An already-prefixed delta_ unit has no offset of its own, which also
    # makes this idempotent - pint can re-apply its preprocessors to an
    # already-processed string.
    offset_names = [
        name for name in units if _is_offset_temperature_unit(registry, name)
    ]
    if not offset_names:
        return result

    is_bare = len(units) == 1 and next(iter(units.values())) == 1

    if is_bare and mode == "on_scale":
        return result

    if not is_bare and mode == "on_scale":
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

    # Replace each offset unit's name token, found with the tokenizer pint
    # itself reads the string with, and keep the rest of the string as is.
    # pint only defines delta_ for the canonical name and its aliases, not
    # for a plural or prefixed spelling ("delta_degrees_C" is undefined).
    pieces = []
    last = 0
    for token in tokenizer(result):
        if token.type == NAME and token.string in offset_names:
            start, end = token.start[1], token.end[1]
            pieces += [result[last:start], f"delta_{registry.get_name(token.string)}"]
            last = end
    pieces.append(result[last:])
    return "".join(pieces)


def _component_temperature_mode(registry: pint.UnitRegistry, cname: str) -> str:
    is_delta = cname.startswith("delta_")
    base_name = cname.removeprefix("delta_") if is_delta else cname

    if registry._is_multiplicative(base_name):
        # No offset at all (e.g. kelvin, degree_rankine) - on_scale and
        # difference are numerically identical and can't be told apart.
        return "unknown"

    return "difference" if is_delta else "on_scale"


def cf_attributes_for(unit: PlainUnit | PlainQuantity) -> dict[str, str]:
    """Work out the CF attributes to write for a Unit or Quantity.

    The reverse of `CFContext`: use it when writing a result, e.g.
    ``ds[name].attrs.update(cf_attributes_for(q))``. It only returns
    ``units_metadata``, and only for temperatures, since CF forbids
    that attribute on other units.

    It reports what pint knows about the unit, not the metadata the
    data was read with:

    - Kelvin and Rankine give ``"temperature: unknown"``: pint has no
      ``delta_`` unit for them, so the unit alone can't tell.
    - If the input had no ``units_metadata``, or ``unknown``, pint
      guessed with the UDUNITS-2 rule (a bare ``degC`` is a
      temperature, ``degC/s`` a difference), which CF quotes as
      guidance only. This function reports that guess as if it were
      known. Keep the original attribute instead, unless your
      computation settled the question (subtracting two temperatures
      gives a difference).

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
