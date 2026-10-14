## v0.3.0

- **Breaking:** `level`, `sigma_level`, `layer` (and their plurals) are now
  always defined by `cf_unitregistry()`, including with
  `cf_extensions=False` - the CF conventions allow these strings in the
  `units` attribute unconditionally (as a COARDS backwards-compatibility
  exception), rather than as an opt-in extension, so
  `cf_extensions=False` previously raising `UndefinedUnitError` for them
  was inaccurate. `cf_extensions=False` still skips the other CF-only
  additions (`practical_salinity_unit`/`psu`, `decibel`/`bel`, the
  `sverdrup`/`Sv` reassignment). Doesn't affect typical usage - only
  relevant if your code specifically expects `UndefinedUnitError` for
  these units in strict mode
- **Breaking:** parsing one of the units above now raises
  `CFDeprecatedUnitWarning` (new public symbol, a `UserWarning` subclass)
  instead of `DeprecationWarning`. `DeprecationWarning` (and
  `FutureWarning`) are silenced by default unless raised from `__main__`,
  which this warning never is - it's always raised from inside pint's own
  parsing, not the caller's code - so in practice it was never visible
  without explicitly enabling warnings; neither category fits anyway,
  since pint-cf isn't planning to remove support for these units.
  `CFDeprecatedUnitWarning` is visible by default and still filterable by
  category (`warnings.filterwarnings("ignore", category=CFDeprecatedUnitWarning)`).
  Doesn't affect typical usage - only relevant if your code specifically
  filters warnings by `DeprecationWarning` category for this case
- Fixed `CFContext(units_metadata="temperature: difference")` raising
  `UndefinedUnitError` for `K` (`'delta_K' is not defined`) - the
  canonical CF temperature anomaly - and for any other unit without an
  offset (`degree_R`, `mK`) or not a temperature at all (`m`). It now only
  resolves an offset temperature unit (`degree_C`, `degree_F`) to its
  `delta_` counterpart; kelvin has no offset, so on-scale and difference
  are the same pint unit. Units metadata on a non-temperature unit (which
  CF forbids) is ignored rather than rejected
- Fixed `CFContext(units_metadata="temperature: on_scale")` raising
  `ValueError` for any compound unit, even without an offset temperature
  unit in it (`m s-1`, `K m-1`, `W m-2 K-1`) - CF allows on_scale on a
  compound unit. It still raises when the compound unit does contain one
  (`degC/s`), since pint can't represent that as on-scale through the
  preprocessor pipeline
- Fixed that `ValueError`'s message, which recommended
  `ureg.Quantity(value, units, as_delta=False)` - a call pint doesn't
  accept. It now points to the route CF (section 3.1.2) describes: when
  the on-scale temperature and the other factors are known separately,
  multiply them as quantities. Forcing the unit with
  `ureg.parse_units(units, as_delta=False)` is deliberately not suggested:
  pint (0.25 and 0.26) converts such units wrongly without raising
- Documented that, with `units_metadata` absent or
  `"temperature: unknown"` (which CF says is ambiguous), pint falls back on
  the UDUNITS rule, and `cf_attributes_for` then reports that guess as
  `on_scale`/`difference` - keep the original attribute when writing such
  data back out
- Fixed `CFContext` with the magnitude inside the string (`ureg("5 degC")`,
  `ureg.Quantity("5 degC")`): `"temperature: difference"` was ignored and
  `"temperature: on_scale"` raised `ValueError` even for a single unit.
  Under `"temperature: difference"`, a compound unit with the magnitude
  inside (`ureg("2 degC/s")`) is now a difference too
- Fixed `CFContext(units_metadata="temperature: difference")` raising
  `UndefinedUnitError` for a plural spelling such as `degrees_C`
- Fixed the `delta_` plurals of Celsius in the registry: the generator
  built them by appending "s" to the singular (`delta_degree_Cs`,
  `delta_degreeCs`, `delta_deg_Cs`) instead of using UDUNITS' own plural,
  so `delta_degrees_C`, `delta_degreesC`, `delta_degs_C` and `delta_degsC`
  were undefined
- Documented that, without `CFContext`, a string with the magnitude inside
  is a pint expression: `ureg("2 degC/s")` gives 275.15 K/s (2 degC
  converted on-scale, then divided), unlike `ureg.Quantity(2, "degC/s")`.
  Read CF data with `ureg.Quantity(values, units)`
- `cf_string_to_pint` is now a pure UDUNITS-to-pint syntax translation:
  the `CFContext` temperature mode is applied by a separate preprocessor,
  bound to the registry, that `cf_unitregistry()` chains right after it.
  Internal change - no effect on `ureg.Quantity`/`ureg.Unit`/`ureg(...)`

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
- Fixed two `CFContext`/`"temperature: difference"` edge cases found during a follow-up test review: an explicit unity power (e.g. `degree_C**1`) was silently treated as on_scale instead of honoring the explicit metadata; a parenthesized bare unit (e.g. `(degree_C)`) produced the invalid `delta_(degree_C)` instead of `delta_degree_Celsius`. Also made the delta\_ prefixing idempotent, since pint can re-run the preprocessor on an already-prefixed string within the same context
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
