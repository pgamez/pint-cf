## v0.2.0

- Fixed [temperature aliases definition](https://github.com/hgrecco/pint/issues/2296)
- Fixed the UDUNITS-2 grammar (`udunits2.lark`) to match the original UDUNITS-2 parser:
  - `per`/`PER` division keyword is now properly case-insensitive (e.g. `"Per"` now works too)
  - Malformed superscript exponents (e.g. `m²⁻`) are now rejected instead of silently producing an invalid pint string
  - `re` is now required in logarithmic units (`lg(re ...)`), matching UDUNITS-2's own grammar
- Simplified timestamp parsing: removed grammar rules/transformer methods whose result was never used, since a shift by timestamp always raises `NotImplementedError` (pint has no time-origin concept)
- Removed a dead `division_fmt` in `CFFormatter`'s long form (it never had any effect on the output)
- Fixed an inverted condition in `tools/xmlrd.py`'s unused `_get_delta_alias` helper and removed the duplicate inline logic it replaces
- Hardened `tools/xmlrd.py` against a fragile `<noplural/>` assumption in the UDUNITS-2 XML

## v0.1.1 (2026-04-08)

Initial release
