## v0.2.1

- Added `THIRD_PARTY_LICENSES.md` and
  `src/pint_cf/resources/registry/UDUNITS2-COPYRIGHT.txt`: the unit
  database this package is built on is redistributed from UDUNITS-2,
  whose license requires its copyright notice to be reproduced -
  needed for the conda-forge submission checklist ("package does not
  vendor other packages... without their license"). Every generated
  registry file now also points to it in its own header comment
- Fixed `tools/xmlrd.py` (the UDUNITS-2 XML → pint registry generator):
  it broke after `cf_string_to_pint` started rejecting numeric-offset
  units (e.g. `K @ 273.15`) outright, since the generator relies on
  that exact string (pint's `"unit; offset: value"` syntax) to define
  `degree_Celsius`/`degree_Fahrenheit` from UDUNITS-2's own XML - valid
  there (a registry definition), unlike as a runtime unit expression.
  Added `_unit_definition_from_udunits`, a private function used only
  by `tools/xmlrd.py` for this - `cf_string_to_pint` itself is
  unchanged, so this doesn't reopen the footgun for any other caller

## v0.2.0

- Added CF units not supported by UDUNITS-2 (#10), on by default in
  `cf_unitregistry()` (pass `cf_extensions=False` to get a plain
  UDUNITS-2-only registry instead), sourced from `cfunits`
  (github.com/NCAS-CMS/cfunits), the CF ecosystem's reference
  implementation for these additions:
  - `level`, `sigma_level`, `layer`: dimensionless vertical-coordinate
    placeholders kept only for COARDS backwards compatibility - parsing
    one raises `DeprecationWarning`, since CF itself calls this use
    deprecated outright
  - `practical_salinity_unit`/`psu` = `1e-3` (not `1`, as CF's own FAQ
    suggests)
  - `decibel`/`dB`, `bel`: plain dimensionless ratio units, matching
    `cfunits`/`cf-units` - the physical reference level a `dB` value is
    relative to depends on the variable's `standard_name`, which is out of
    scope for a unit-string converter
  - Reassigned the `Sv` symbol from `sievert` to `sverdrup`, matching CF/
    `cfunits` instead of UDUNITS-2's own SI-based choice; also fixed `rem`
    (defined upstream as `cSv`) so it keeps meaning centisievert instead of
    being silently corrupted into a fraction of a sverdrup by the
    reassignment
- Added `CFContext`, a context manager for CF's `units_metadata` attribute (CF-1.11, #9): forces a bare temperature unit to its `delta_` counterpart under `"temperature: difference"`, honored transparently by native pint calls (`ureg.Quantity(...)`, `ureg(...)`) - no pint-cf-specific replacement needed. `"temperature: unknown"`/absent needs no special handling, since pint's own default `as_delta=True` already applies UDUNITS' compound-expression heuristic. `"temperature: on_scale"` on a compound expression raises `ValueError`, since it can't be honored through the preprocessor pipeline (use `ureg.Quantity(value, units, as_delta=False)` directly for that rare case)
- Added `cf_attributes_for(unit_or_quantity)`, the reverse of `CFContext`: derives CF variable attributes (currently just `units_metadata`) from an already-computed Unit/Quantity as a dict, ready to merge into a NetCDF variable's attributes. Returns `{}` for a non-temperature unit, and `{"units_metadata": "temperature: unknown"}` for Kelvin/Rankine, which have no offset and therefore no `delta_` counterpart - on_scale and difference are numerically identical for them and cannot be recovered from the unit alone
- Fixed two `CFContext`/`"temperature: difference"` edge cases found during a follow-up test review: an explicit unity power (e.g. `degree_C**1`) was silently treated as on_scale instead of honoring the explicit metadata; a parenthesized bare unit (e.g. `(degree_C)`) produced the invalid `delta_(degree_C)` instead of `delta_degree_Celsius`. Also made the delta_ prefixing idempotent, since pint can re-run the preprocessor on an already-prefixed string within the same context
- Fixed a shift-by-number unit (e.g. `K @ 273.15`, `a from 1`) always crashing downstream with a confusing, unrelated pint error (`Unit expression cannot have a scaling factor.`): the transform previously produced pint's `"unit; offset: value"` syntax, which is only valid when *defining* a new named unit, not as a runtime unit expression - `cf_string_to_pint` now raises `NotImplementedError` explicitly instead, with a pointer to `ureg.define(...)` as the manual workaround
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
