"""
TODO:

- https://docs.unidata.ucar.edu/udunits/current/udunits2lib.html#Grammar
- fechas (tienen el signo -)
- # ("days since 1970-01-01", "a; offset: 1"), -> not implemented error
- El XML tambien se tiene que probar

"""

import pytest

# from cfunits import Units
from lark.exceptions import UnexpectedInput, VisitError
from pint.delegates import ParserConfig
from pint.delegates.txt_defparser.plain import UnitDefinition

from pint_cf.parser import cf_string_to_pint

TEST_CASES_TRANSFORM = [
    # =========================================================================
    # Unit-Spec: nothing
    # =========================================================================
    ("", ""),
    ("1", ""),
    # =========================================================================
    # Basic-Spec → ID: simple identifiers
    # =========================================================================
    ("a", "a"),
    ("m", "m"),
    ("kg", "kg"),
    ("kilogram", "kilogram"),
    ("degrees_Celsius", "degrees_Celsius"),
    ("degrees_north", "degrees_north"),
    ("degrees_east", "degrees_east"),
    ("hPa", "hPa"),
    ("dBm", "dBm"),
    # Special symbol IDs
    ("°", "°"),
    ("°F", "°F"),
    # ("µ", "µ"),
    ("'", "arc_minute"),
    ('"', "arc_second"),
    ("'/60", "arc_minute / 60"),
    # =========================================================================
    # Basic-Spec → Number: INT and REAL
    # =========================================================================
    ("2", "2"),
    ("10", "10"),
    ("100", "100"),
    ("+1", "+1"),
    ("-1", "-1"),
    ("3.14", "3.14"),
    ("1.0", "1.0"),
    ("1.", "1."),
    (".1", ".1"),
    (".5", ".5"),
    ("0.5", "0.5"),
    ("0.01", "0.01"),
    ("1e10", "1e10"),
    ("1.0e3", "1.0e3"),
    ("1.0e-3", "1.0e-3"),
    ("1e-6", "1e-6"),
    # =========================================================================
    # Basic-Spec → "(" Shift-Spec ")" : parenthesized groups
    # =========================================================================
    ("(m)", "(m)"),
    ("(kg)", "(kg)"),
    ("(m/s)", "(m / s)"),
    ("(m/s^2)", "(m / s ** 2)"),
    ("(kg/m^3)", "(kg / m ** 3)"),
    ("(m^2/s)", "(m ** 2 / s)"),
    ("(m/(s K))", "(m / (s * K))"),
    ("((m))", "((m))"),
    # =========================================================================
    # Power-Spec → Basic-Spec INT : trailing digits as exponent
    # =========================================================================
    ("a2", "a ** 2"),
    ("m3", "m ** 3"),
    ("s1", "s ** 1"),
    # Negative trailing exponent
    ("a-2", "a ** -2"),
    ("s-1", "s ** -1"),
    ("m-s-2", "m * s ** -2"),
    # =========================================================================
    # Power-Spec → Basic-Spec EXPONENT : unicode superscripts (¹²³)
    # =========================================================================
    ("a¹", "a ** 1"),
    ("a²", "a ** 2"),
    ("a³", "a ** 3"),
    ("m²", "m ** 2"),
    ("m³", "m ** 3"),
    ("kg³", "kg ** 3"),
    ("s¹", "s ** 1"),
    # Multi-digit superscript
    ("m¹²", "m ** 12"),
    # =========================================================================
    # Power-Spec → Basic-Spec RAISE INT : ^ or **
    # =========================================================================
    ("a^2", "a ** 2"),
    ("a**2", "a ** 2"),
    ("a^-2", "a ** -2"),
    ("a**-2", "a ** -2"),
    ("m^3", "m ** 3"),
    ("m**3", "m ** 3"),
    ("m^-1", "m ** -1"),
    ("m**-1", "m ** -1"),
    ("s^-2", "s ** -2"),
    ("s**-2", "s ** -2"),
    ("K^-1", "K ** -1"),
    ("m^1", "m ** 1"),
    ("m^0", "m ** 0"),
    ("m**0", "m ** 0"),
    ("m^10", "m ** 10"),
    ("m^+2", "m ** +2"),
    # Power of group
    ("(m)^2", "(m) ** 2"),
    ("(m/s)^2", "(m / s) ** 2"),
    ("(m/s)^-1", "(m / s) ** -1"),
    ("(m/s)^-2", "(m / s) ** -2"),
    ("(kg m)^2", "(kg * m) ** 2"),
    ("(kg m)^-1", "(kg * m) ** -1"),
    # =========================================================================
    # Product-Spec → MULTIPLY : all multiplication operators
    # =========================================================================
    # Dash (-)
    ("a-b", "a * b"),
    # Dot (.)
    ("a.b", "a * b"),
    # Asterisk (*)
    ("a*b", "a * b"),
    # Space / juxtaposition
    ("a b", "a * b"),
    ("a  b", "a * b"),
    ("m 2", "m * 2"),
    ("kg m 2", "kg * m * 2"),
    # Centered middot (·)
    ("a·b", "a * b"),
    # Chained multiply (3+ terms)
    ("kg m s", "kg * m * s"),
    ("m.s.K", "m * s * K"),
    ("m*s*K", "m * s * K"),
    # Products with exponents
    ("m^2.s^-1", "m ** 2 * s ** -1"),
    ("kg.m.s^-2", "kg * m * s ** -2"),
    ("meter-second^-1", "meter * second ** -1"),
    ("meter-second**-2", "meter * second ** -2"),
    # =========================================================================
    # Product-Spec → DIVIDE : all division operators
    # =========================================================================
    ("a/b", "a / b"),
    ("a / b", "a / b"),
    ("a  /  b", "a / b"),
    ("a per b", "a / b"),
    ("a PER b", "a / b"),
    ("kg  /  m", "kg / m"),
    # Chained division
    ("m/s/K", "m / s / K"),
    ("kg/m/s", "kg / m / s"),
    ("m / s / K", "m / s / K"),
    # Per with exponents
    ("kg per s^2", "kg / s ** 2"),
    ("W per m^2", "W / m ** 2"),
    ("m^2 per s", "m ** 2 / s"),
    ("m^2 per s^2", "m ** 2 / s ** 2"),
    ("m^2 PER s^2", "m ** 2 / s ** 2"),
    # Division of groups
    ("(m)/(s)", "(m) / (s)"),
    # =========================================================================
    # Product-Spec → mixed multiply + divide
    # =========================================================================
    ("kg*m/s", "kg * m / s"),
    ("kg m/s", "kg * m / s"),
    ("kg m / s", "kg * m / s"),
    ("kg m / s^2", "kg * m / s ** 2"),
    ("kg m -2", "kg * m * -2"),
    ("kg.m/s2", "kg * m * s ** -2"),
    ("1/s", "1 / s"),
    ("1/m", "1 / m"),
    ("1/s^2", "1 / s ** 2"),
    ("1 m/s", "1 * m / s"),
    ("g/kg", "g / kg"),
    # =========================================================================
    # Shift-Spec → Product-Spec SHIFT INT
    # =========================================================================
    ("a @ 1", "a; offset: 1"),
    ("a after 1", "a; offset: 1"),
    ("a from 1", "a; offset: 1"),
    ("a ref 1", "a; offset: 1"),
    ("K @ 0", "K; offset: 0"),
    # =========================================================================
    # Shift-Spec → Product-Spec SHIFT REAL
    # =========================================================================
    ("K @ 273.15", "K; offset: 273.15"),
    ("K @ -273.15", "K; offset: -273.15"),
    ("a @ 1.5", "a; offset: 1.5"),
    ("K after 273.15", "K; offset: 273.15"),
    ("K from 273.15", "K; offset: 273.15"),
    ("K ref 273.15", "K; offset: 273.15"),
    ("degC @ 1.5", "degC; offset: 1.5"),
    ("°R @ 459.67", "°R; offset: 459.67"),
    # Shift on product expression
    ("m/s @ 0", "m / s; offset: 0"),
    # =========================================================================
    # Basic-Spec → LOGREF Product-Spec ")" : logarithmic units
    # =========================================================================
    # All log types with reference value
    ("log(re 1 a)", "1 * a; logbase: 10; logfactor: 10"),
    ("lg(re 1 a)", "1 * a; logbase: 10; logfactor: 10"),
    ("ln(re 1 a)", "1 * a; logbase: 2.718281828459045; logfactor: 0.5"),
    ("lb(re 1 a)", "1 * a; logbase: 2; logfactor: 1"),
    # With colon in "re:"
    ("lb ( re: 1 a)", "1 * a; logbase: 2; logfactor: 1"),
    ("ln(re: 1 Pa)", "1 * Pa; logbase: 2.718281828459045; logfactor: 0.5"),
    # With real unit names
    ("lg(re 1 mW)", "1 * mW; logbase: 10; logfactor: 10"),
    ("ln(re 1 Pa)", "1 * Pa; logbase: 2.718281828459045; logfactor: 0.5"),
    ("lb(re 1 W)", "1 * W; logbase: 2; logfactor: 1"),
    # Without reference number
    ("lg(re mW)", "mW; logbase: 10; logfactor: 10"),
    ("lb(re W)", "W; logbase: 2; logfactor: 1"),
    # Colon without number
    ("lb(re: W)", "W; logbase: 2; logfactor: 1"),
    ("lg(re: mW)", "mW; logbase: 10; logfactor: 10"),
    # =========================================================================
    # Complex / Real-world CF-convention expressions
    # =========================================================================
    # SI derived units with exponents
    ("kg m^2 s^-2", "kg * m ** 2 * s ** -2"),
    ("kg m^2 s^-2 K^-1", "kg * m ** 2 * s ** -2 * K ** -1"),
    ("kg m^-1 s^-2", "kg * m ** -1 * s ** -2"),
    ("kg^1 m^2 s^-3", "kg ** 1 * m ** 2 * s ** -3"),
    ("W m^-2", "W * m ** -2"),
    ("mol kg^-1", "mol * kg ** -1"),
    ("m^2 s^-1", "m ** 2 * s ** -1"),
    # Division with parenthesized denominators
    ("W/(m^2)", "W / (m ** 2)"),
    ("J/(kg K)", "J / (kg * K)"),
    ("kg/(m s)", "kg / (m * s)"),
    ("kg / (m s^2)", "kg * m ** -1 * s ** -2"),
    ("W/(m^2 K)", "W / (m ** 2 * K)"),
    ("m^2/(s^2 K)", "m ** 2 / (s ** 2 * K)"),
    ("kg m^2/(s^2 K mol)", "kg * m ** 2 / (s ** 2 * K * mol)"),
    # Scalar * unit
    ("0.001 m", "0.001 * m"),
    ("1000 kg", "1000 * kg"),
    ("m 1.5", "1.5 * m"),
    ("1e3 Pa", "1e3 * Pa"),
    ("Pa 1e3", "1e3 * Pa"),
    ("1e-3 m", "1e-3 * m"),
    ("1e-6 m", "1e-6 * m"),
    ("2 m^2", "2 * m ** 2"),
    ("0.5 kg^-1", "0.5 * kg ** -1"),
    ("0.1 Pa", "0.1 * Pa"),
    # Common CF convention units
    ("Pa s", "Pa * s"),
    ("N m", "N * m"),
    ("mm/day", "mm / day"),
    ("W/m^2", "W / m ** 2"),
    ("K/m", "K / m"),
    ("mol/m^3", "mol / m ** 3"),
    ("m/s^2", "m / s ** 2"),
    # =========================================================================
    # Whitespace handling
    # =========================================================================
    ("  m  ", "m"),
    ("  m    /    s^2    ", "m / s ** 2"),
    ("  kg  /  s  ", "kg / s"),
    # =========================================================================
    # Additional units and symbols from CF conventions (not in UDUNITS)
    # =========================================================================
    ("level", "level"),
    ("layer", "layer"),
    ("sigma_level", "sigma_level"),
    ("sigma_level * 10", "sigma_level * 10"),
]


TEST_CASES_TIME_SHIFTS = [
    "seconds since 1970-01-01",
    "seconds since 1970-01-01 12:34",
    "seconds since 1970-01-01 12:34 +01:00",
    "seconds since 1970-01-01 12:34 UTC",
    "seconds since 1970-01-01T12:34",
    "seconds since 1970-01-01T12:34 Z",
    "seconds since 19700101T1234",
    "seconds since 19700101T1234 +01:00",
    "seconds since 19700101T1234 UTC",
]


TEST_CASES_INVALID = [
    # =========================================================================
    # Invalid operators / syntax
    # =========================================================================
    # Double slash, double plus
    "a // b",
    "a ++ b",
    # Double raise
    "a^^2",
    "a ^ ^ 2",
    # Double consecutive operators
    "a * * b",
    "a / / b",
    # Mixed invalid operators
    "a*/b",
    "a/*b",
    "m ^^ 2",
    # =========================================================================
    # Trailing operators (incomplete expressions)
    # =========================================================================
    "a/",
    "a*",
    "a^",
    "a**",
    "m per",
    "m since",
    "K @",
    # =========================================================================
    # Leading operators (missing left operand)
    # =========================================================================
    "/m",
    "*m",
    "^m",
    "/ s",
    "* s",
    "^ 2",
    "^2",
    "**2",
    "@ 1",
    # =========================================================================
    # Unmatched / empty parentheses
    # =========================================================================
    "()",
    "( )",
    "(  )",
    "(m",
    "((m)",
    # =========================================================================
    # Invalid characters (not part of <alpha>, <digit>, or operators)
    # =========================================================================
    "!m",
    "#kg",
    "$m",
    "&m",
    "~m",
    "m~",
    "?m",
    # Invalid delimiters
    "m[2]",
    "m{2}",
    "m<2>",
    "a=b",
    "a+b",
    "m,s",
    "m;s",
    # =========================================================================
    # Only operators (no operands)
    # =========================================================================
    "*",
    "/",
    "^",
    "**",
    "@",
    # =========================================================================
    # Nonsense strings
    # =========================================================================
    "!!!",
    "---",
    "...",
    "@@@",
    # =========================================================================
    # Invalid number format
    # =========================================================================
    "1e+",
    # =========================================================================
    # Invalid shift expressions
    # =========================================================================
    # Double shift
    "K @ 1 @ 2",
    # Shift with parenthesized offset (not allowed)
    "K @ (1)",
    # =========================================================================
    # Invalid LOGREF expressions
    # =========================================================================
    # Missing closing paren
    "log(re 1 mW",
    # Missing opening paren
    "log mW)",
    # Empty log
    "log()",
    "lg()",
    "ln()",
    "lb()",
]


@pytest.mark.parametrize("input_str, expected_str", TEST_CASES_TRANSFORM)
def test_transform(input_str: str, expected_str: str) -> None:
    import warnings

    u = cf_string_to_pint(input_str)
    cfg = ParserConfig()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        result = UnitDefinition.from_string_and_config(f"_ = {u}", cfg)
        expected = UnitDefinition.from_string_and_config(f"_ = {expected_str}", cfg)

    assert result == expected, (
        f"Expected '{expected}', got '{result}' for input '{input_str}'"
    )


@pytest.mark.parametrize("input_str", TEST_CASES_INVALID)
def test_invalid_raises(input_str: str) -> None:
    """Strings that violate the grammar must raise an exception when parsed."""
    with pytest.raises(UnexpectedInput):
        cf_string_to_pint(input_str)


@pytest.mark.parametrize("input_str", TEST_CASES_TIME_SHIFTS)
def test_time_shifts_raise_not_implemented(input_str: str) -> None:
    with pytest.raises(
        VisitError, match="Time-based offsets are not directly supported by pint"
    ):
        cf_string_to_pint(input_str)
