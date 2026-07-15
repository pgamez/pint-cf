"""
UDUNITS-2 to Pint String Transformer

Converts Lark parse trees from udunits2.lark into strings
that can be parsed directly by pint.
"""

from pathlib import Path

from lark import Lark, Token, Transformer, v_args

from .context import _apply_standard_name_reference, _apply_temperature_mode

# Unicode superscript to ASCII digit mapping
_SUPERSCRIPT_MAP = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
}

_ANGLE_SYMBOL_REPLACEMENTS = {
    "'": "arc_minute",
    '"': "arc_second",
}


def _decode_superscript(s: str) -> str:
    """Convert unicode superscript characters to regular digits."""
    return "".join(_SUPERSCRIPT_MAP.get(c, c) for c in s)


def _normalize_identifier(name: str) -> str:
    """Normalize UDUNITS symbols that need explicit pint unit names."""
    for symbol, replacement in _ANGLE_SYMBOL_REPLACEMENTS.items():
        name = name.replace(symbol, replacement)
    return name


def _split_id_with_exponent(token_str: str) -> tuple[str, str]:
    """Split trailing signed integer exponent from an identifier token."""
    idx = len(token_str)
    while idx > 0 and token_str[idx - 1].isdigit():
        idx -= 1

    # The grammar guarantees that exponent digits exist at the end.
    if idx == len(token_str):
        raise ValueError(f"ID_WITH_EXP token without trailing digits: {token_str}")

    if idx > 0 and token_str[idx - 1] == "-":
        idx -= 1

    base_name = token_str[:idx]
    exponent = token_str[idx:]

    if not base_name or not exponent:
        raise ValueError(f"Invalid ID_WITH_EXP token: {token_str}")

    return base_name, exponent


@v_args(inline=True)
class UdunitsToPintTransformer(Transformer):
    """Transform a Lark parse tree into a pint-parseable string.

    The parse tree is produced from `udunits2.lark` by the parser
    returned by `get_parser`.

    Parameters
    ----------
    allow_numeric_shift : bool, optional
        Internal - only ``tools/xmlrd.py`` (the registry generator)
        constructs this with ``True``; `cf_string_to_pint` always uses
        the default. When ``False`` (the default), a numeric offset
        unit (e.g. ``"K @ 273.15"``) raises `NotImplementedError`,
        since pint's offset syntax it would otherwise produce only
        works when *defining* a new named unit, not as a runtime unit
        expression - see `shift_by_number`.

    Examples
    --------
    >>> transformer = UdunitsToPintTransformer()
    >>> parser = get_parser()
    >>> tree = parser.parse("kg.m/s2")
    >>> transformer.transform(tree)
    'kg * m / s ** 2'
    """

    def __init__(self, *, allow_numeric_shift: bool = False) -> None:
        super().__init__()
        self._allow_numeric_shift = allow_numeric_shift

    # -------------------------------------------------------------------------
    # Numbers
    # -------------------------------------------------------------------------

    @staticmethod
    def _binary_operands(args: tuple) -> tuple[str, str]:
        """Return left/right operands for binary forms with optional operator token."""
        if len(args) == 2:
            return args[0], args[1]
        if len(args) == 3:
            return args[0], args[2]
        raise ValueError(f"Unexpected binary args: {args}")

    def int(self, value: Token) -> str:
        """Integer literal."""
        return str(value)

    def real(self, value: Token) -> str:
        """Real number literal."""
        return str(value)

    def scalar(self, value: str) -> str:
        """Scalar value (passes through)."""
        return value

    # -------------------------------------------------------------------------
    # Identifiers
    # -------------------------------------------------------------------------

    def identifier(self, name: Token) -> str:
        """
        Unit identifier (e.g., 'm', 'kilogram', '°').
        """
        return _normalize_identifier(str(name))

    def power_from_id(self, name: Token) -> str:
        """Power notation encoded in identifier token (e.g., 'm2', 's-1')."""
        base_name, exponent = _split_id_with_exponent(str(name))
        return f"{base_name} ** {exponent}"

    # -------------------------------------------------------------------------
    # Arithmetic operations
    # -------------------------------------------------------------------------

    def multiply(self, *args) -> str:
        """
        Multiplication (explicit or implicit via juxtaposition).
        """
        left, right = self._binary_operands(args)
        return f"{left} * {right}"

    def divide(self, *args) -> str:
        """Division."""
        left, right = self._binary_operands(args)
        return f"{left} / {right}"

    def power(self, base: str, *args) -> str:
        """
        Exponentiation. Handles multiple forms:
        - basic_exp EXPONENT (e.g., m²)
        - basic_exp RAISE INTEGER (e.g., m^2, m**2)
        """
        if len(args) == 1:
            exp_token = args[0]
        elif len(args) == 2:
            # RAISE INTEGER - skip the RAISE operator
            exp_token = args[1]
        else:
            raise ValueError(f"Unexpected power args: {args}")

        exp_str = str(exp_token)

        # Handle unicode superscripts
        if any(c in _SUPERSCRIPT_MAP for c in exp_str):
            exp_str = _decode_superscript(exp_str)

        return f"{base} ** {exp_str}"

    # -------------------------------------------------------------------------
    # Grouping
    # -------------------------------------------------------------------------

    def group(self, inner: str) -> str:
        """Parenthetical group."""
        return f"({inner})"

    # -------------------------------------------------------------------------
    # Logarithms
    # -------------------------------------------------------------------------

    # Mapping from UDUNITS log types to pint logbase/logfactor
    _LOG_PARAMS = {
        "lg": ("10", "10"),  # log base 10, decibels
        "log": ("10", "10"),  # log base 10, decibels (alias)
        "ln": (
            "2.71828182845904523536028747135266249775724709369995",
            "0.5",
        ),  # natural log, neper
        "lb": ("2", "1"),  # log base 2, octaves
    }

    def logarithm(self, logref: Token, argument: str) -> str:
        """
        Logarithmic units (e.g., lg(re 1 mW), ln(re Pa)).

        Converts to pint's logarithmic unit format:
          scale; logbase: X; logfactor: Y
        """
        logref_str = str(logref).strip().lower()

        # Determine log type
        if logref_str.startswith("log"):
            log_type = "log"
        elif logref_str.startswith("lg"):
            log_type = "lg"
        elif logref_str.startswith("ln"):
            log_type = "ln"
        elif logref_str.startswith("lb"):
            log_type = "lb"
        else:
            log_type = "lg"  # default to decibels

        logbase, logfactor = self._LOG_PARAMS.get(log_type, ("10", "10"))

        return f"{argument}; logbase: {logbase}; logfactor: {logfactor}"

    # -------------------------------------------------------------------------
    # Time shifts (offset units)
    # -------------------------------------------------------------------------

    def shift_op(self, op: Token) -> str:
        """Extract shift operator type."""
        return str(op).lower()

    def shift_by_number(self, unit: str, shift_op: str, offset: str) -> str:
        """
        Shift by numeric offset (e.g., K @ 273.15).

        pint's own offset notation ("unit; offset: value") is only valid
        when defining a NEW named unit in a registry file - it can't be
        parsed as a runtime unit expression by Quantity()/Unit()/ureg(),
        so there is no pint spelling of this that would actually work for
        a caller. Rejected explicitly (unless `allow_numeric_shift` was
        passed to the constructor) rather than returning a string that
        looks valid here but always fails downstream with a confusing,
        unrelated pint error.
        """
        if self._allow_numeric_shift:
            return f"{unit}; offset: {offset}"

        raise NotImplementedError(
            "Numeric offset units (e.g. 'K @ 273.15') are not directly "
            "supported: pint's offset syntax ('unit; offset: value') only "
            "works when defining a new named unit, not as a runtime unit "
            "expression. Define the shifted unit explicitly instead, e.g. "
            "ureg.define('my_unit = kelvin; offset: 273.15')."
        )

    def shift_by_time(self, unit: str, shift_op: str, timestamp) -> str:
        """
        Shift by timestamp (e.g., seconds since 1970-01-01).

        pint has no notion of a time origin, so this is always rejected. The
        grammar still parses the timestamp (rather than treating it as a syntax
        error) purely so this explicit message can be raised instead - its
        parsed value is otherwise unused.
        """
        raise NotImplementedError(
            "Time-based offsets are not directly supported by pint. "
            "Consider using a dedicated time handling library like cftime "
            "for this use case (see: https://unidata.github.io/cftime/)"
        )


# =============================================================================
# Convenience functions
# =============================================================================

_parser = None


def get_parser() -> Lark:
    """Get the UDUNITS-2 parser.

    Returns
    -------
    lark.Lark
        A parser built from `udunits2.lark`, cached after the
        first call.
    """
    global _parser
    if _parser is None:
        grammar_path = Path(__file__).parent / "resources" / "udunits2.lark"
        _parser = Lark(
            grammar_path.read_text(),
            parser="lalr",
            lexer="contextual",
            maybe_placeholders=False,
        )
    return _parser


def cf_string_to_pint(unit_string: str) -> str:
    """Convert a UDUNITS-2 unit string to pint-compatible format.

    Under an active `pint_cf.CFContext`, the CF ``units_metadata``
    temperature mode is applied: ``"difference"`` forces a bare
    temperature unit to its ``delta_`` counterpart, e.g.
    ``"degree_C"`` -> ``"delta_degree_Celsius"``. With no active
    context (or ``"unknown"``), behavior is unchanged - pint's own
    default ``as_delta=True`` already applies UDUNITS' compound
    expression heuristic.

    Likewise, under an active `pint_cf.CFContext` with a recognized
    ``standard_name``, a bare ``"dB"``/``"decibel"`` is resolved to the
    (private, pint-cf-internal) pint unit carrying that standard name's
    physical reference level, e.g. ``"dB"`` ->
    ``"_dB_sound_pressure_level_in_air"``. With no active context (or an
    unrecognized standard_name), it stays the plain dimensionless ratio
    unit.

    Parameters
    ----------
    unit_string : str
        A unit specification in UDUNITS-2 format.

    Returns
    -------
    str
        A string that pint can parse directly.

    Raises
    ------
    NotImplementedError
        For a shift by timestamp (e.g. "seconds since
        1970-01-01") - pint has no notion of a time origin. Also for
        a shift by number (e.g. "K @ 273.15") - pint's offset syntax
        only works when defining a new named unit, not as a runtime
        unit expression.
    ValueError
        For ``"temperature: on_scale"`` applied to a compound unit
        expression - it can't be honored through the automatic
        preprocessor pipeline; call
        ``ureg.Quantity(value, units, as_delta=False)`` directly
        instead.

    Examples
    --------
    >>> cf_string_to_pint("m")
    'm'
    >>> cf_string_to_pint("m2")
    'm ** 2'
    >>> cf_string_to_pint("kg.m/s2")
    'kg * m / s ** 2'

    """
    if not unit_string or unit_string.isspace():
        return "1"

    parser = get_parser()
    transformer = UdunitsToPintTransformer()

    tree = parser.parse(unit_string)

    if tree is None or (hasattr(tree, "children") and len(tree.children) == 0):
        return "1"

    result = transformer.transform(tree)

    if not isinstance(result, str):
        return "1"

    return _apply_standard_name_reference(_apply_temperature_mode(result))
