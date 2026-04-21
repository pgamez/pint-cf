"""
UDUNITS-2 to Pint String Transformer

Converts Lark parse trees from udunits2.lark into strings
that can be parsed directly by pint.
"""

import warnings
from pathlib import Path

from lark import Lark, Token, Transformer, v_args

# Additional adimensional units that are in the CF standard but not in UDUNITS2

ADDITIONAL_ADIMENSIONAL_UNITS = {
    "level": (
        "The use of 'level' is deprecated in the CF standard."
        " but accepted for backward compatibility with COARDS."
        " Conventions for more precisely identifying dimensionless vertical"
        " coordinates are available.",
        FutureWarning,
    ),
    "layer": (
        "The use of 'layer' is deprecated in the CF standard."
        " but accepted for backward compatibility with COARDS."
        " Conventions for more precisely identifying dimensionless vertical"
        " coordinates are available.",
        FutureWarning,
    ),
    "sigma_level": (
        "The use of 'sigma_level' is deprecated in the CF standard."
        " but accepted for backward compatibility with COARDS."
        " Conventions for more precisely identifying dimensionless vertical"
        " coordinates are available.",
        FutureWarning,
    ),
}

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
    """
    Transform a Lark parse tree from udunits2.lark into a string
    that pint can parse directly.

    Example:
        >>> transformer = UdunitsToPintTransformer()
        >>> parser = get_parser()
        >>> tree = parser.parse("kg.m/s2")
        >>> result = transformer.transform(tree)
        >>> print(result)  # "kg * m / s ** 2"
    """

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
        identifier = _normalize_identifier(str(name))
        if message := ADDITIONAL_ADIMENSIONAL_UNITS.get(identifier.strip()):
            warnings.warn(*message, stacklevel=2)
        return identifier

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

        Uses pint's offset notation: "unit; offset: value"
        """
        return f"{unit}; offset: {offset}"

    def shift_by_time(self, unit: str, shift_op: str, timestamp: str) -> str:
        """
        Shift by timestamp (e.g., seconds since 1970-01-01).

        Creates a special notation for time references.
        """
        # return f"{unit} since {timestamp}"
        raise NotImplementedError(
            "Time-based offsets are not directly supported by pint. "
            "Consider using a dedicated time handling library like cftime "
            "for this use case (see: https://unidata.github.io/cftime/)"
        )

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------

    def date_only(self, date: Token) -> str:
        """Date without time (e.g., 1970-01-01)."""
        return str(date)

    def date_time(self, date: Token, clock: Token) -> str:
        """Date with time (e.g., 1970-01-01 00:00:00)."""
        return f"{date} {clock}"

    def date_time_offset(self, date: Token, clock: Token, offset: Token) -> str:
        """Date with time and timezone offset."""
        return f"{date} {clock} {offset}"

    def date_time_tz(self, date: Token, clock: Token, tz: Token) -> str:
        """Date with time and timezone identifier."""
        return f"{date} {clock} {tz}"

    def datetime_iso(self, dt: Token) -> str:
        """ISO 8601 datetime (e.g., 1970-01-01T00:00:00)."""
        return str(dt)

    def datetime_iso_tz(self, dt: Token, tz: Token) -> str:
        """ISO 8601 datetime with timezone."""
        return f"{dt} {tz}"

    def packed_timestamp(self, ts: Token) -> str:
        """Packed timestamp (e.g., 19700101T000000)."""
        return str(ts)

    def packed_timestamp_offset(self, ts: Token, offset: Token) -> str:
        """Packed timestamp with offset."""
        return f"{ts} {offset}"

    def packed_timestamp_tz(self, ts: Token, tz: Token) -> str:
        """Packed timestamp with timezone."""
        return f"{ts} {tz}"


# =============================================================================
# Convenience functions
# =============================================================================

_parser = None


def get_parser() -> Lark:
    """Get the UDUNITS-2 parser (cached)."""
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
    """
    Convert a UDUNITS-2 unit string to pint-compatible format.

    Args:
        unit_string: A unit specification in UDUNITS-2 format.

    Returns:
        A string that pint can parse directly.

    Examples:
        >>> udunits_to_pint("m")
        'm'
        >>> udunits_to_pint("m2")
        'm ** 2'
        >>> udunits_to_pint("kg.m/s2")
        'kg * m / s ** 2'
        >>> udunits_to_pint("K @ 273.15")
        'K; offset: 273.15'
        >>> udunits_to_pint("seconds since 1970-01-01")
        'seconds since 1970-01-01'
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

    return result
