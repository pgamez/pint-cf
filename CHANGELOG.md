## v0.2.0

- Added `CFContext`, a context manager for CF's `units_metadata` attribute (CF-1.11, #9): forces a bare temperature unit to its `delta_` counterpart under `"temperature: difference"`, honored transparently by native pint calls (`ureg.Quantity(...)`, `ureg(...)`) - no pint-cf-specific replacement needed. `"temperature: unknown"`/absent needs no special handling, since pint's own default `as_delta=True` already applies UDUNITS' compound-expression heuristic. `"temperature: on_scale"` on a compound expression raises `ValueError`, since it can't be honored through the preprocessor pipeline (use `ureg.Quantity(value, units, as_delta=False)` directly for that rare case)
- Added `cf_attributes_for(unit_or_quantity)`, the reverse of `CFContext`: derives CF variable attributes (currently just `units_metadata`) from an already-computed Unit/Quantity as a dict, ready to merge into a NetCDF variable's attributes. Returns `{}` for a non-temperature unit, and `{"units_metadata": "temperature: unknown"}` for Kelvin/Rankine, which have no offset and therefore no `delta_` counterpart - on_scale and difference are numerically identical for them and cannot be recovered from the unit alone
- Fixed two `CFContext`/`"temperature: difference"` edge cases found during a follow-up test review: an explicit unity power (e.g. `degree_C**1`) was silently treated as on_scale instead of honoring the explicit metadata; a parenthesized bare unit (e.g. `(degree_C)`) produced the invalid `delta_(degree_C)` instead of `delta_degree_Celsius`. Also made the delta_ prefixing idempotent, since pint can re-run the preprocessor on an already-prefixed string within the same context
- Fixed [temperature aliases definition](https://github.com/hgrecco/pint/issues/2296)
- Fixed the UDUNITS-2 grammar (`udunits2.lark`) to match the original UDUNITS-2 parser:
  - `per`/`PER` division keyword is now properly case-insensitive (e.g. `"Per"` now works too)
  - Malformed superscript exponents (e.g. `m²⁻`) are now rejected instead of silently producing an invalid pint string
  - `re` is now required in logarithmic units (`lg(re ...)`), matching UDUNITS-2's own grammar
- Simplified timestamp parsing: removed grammar rules/transformer methods whose result was never used, since a shift by timestamp always raises `NotImplementedError` (pint has no time-origin concept)
- Removed a dead `division_fmt` in `CFFormatter`'s long form (it never had any effect on the output)
- Fixed an inverted condition in `tools/xmlrd.py`'s unused `_get_delta_alias` helper and removed the duplicate inline logic it replaces
- Hardened `tools/xmlrd.py` against a fragile `<noplural/>` assumption in the UDUNITS-2 XML
- Resynced `tools/xml/*.xml` with upstream UDUNITS-2 (fixes `footcandle`'s conversion factor)

## v0.1.1 (2026-04-08)

Initial release
