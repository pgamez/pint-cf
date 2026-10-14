## v0.3.0

### Breaking changes

- `level`, `sigma_level` and `layer` are now always defined, also with
  `cf_extensions=False`. CF allows them unconditionally, so they aren't an
  optional extension.
- Those units now warn with `CFDeprecatedUnitWarning` (new, a
  `UserWarning`) instead of `DeprecationWarning`. Python hid the old
  warning by default, so nobody saw it. Filter the new one with
  `warnings.filterwarnings("ignore", category=CFDeprecatedUnitWarning)`.

### Fixes

Temperatures with `CFContext`:

- `"temperature: difference"` with kelvin (`K`, `mK`) or Rankine raised
  `UndefinedUnitError`. It now works. Pint has no `delta_` unit for them,
  so read and convert inside the block (see the README).
- `"temperature: difference"` with a plural (`degrees_C`) raised
  `UndefinedUnitError`. It now works.
- `"temperature: on_scale"` raised `ValueError` for any compound unit
  (`m s-1`, `W m-2 K-1`). It now only raises when the compound unit has
  Celsius or Fahrenheit in it (`degC/s`): CF says that can only be
  converted with the temperature and the other factors known separately.
- That error suggested `ureg.Quantity(value, units, as_delta=False)`, which
  pint doesn't accept. It now suggests multiplying the temperature and the
  rest as separate quantities, as CF describes.
- With the value inside the string (`ureg("5 degC")`), the metadata was
  ignored or raised `ValueError`. It now applies as with
  `ureg.Quantity(5, "degC")`.
- `units_metadata` on a unit that isn't a temperature (`m`) raised an
  error. It's now ignored, as CF forbids it there.

Parsing and registry:

- An exponent right after a parenthesis, as in `(m s)-1` or `(m-1)-1`, was
  rejected. It's now an exponent, as in UDUNITS-2. This makes the CF
  standard name table's `W m-2 sr-1 (m-1)-1` readable.
- `delta_degrees_C`, `delta_degreesC`, `delta_degs_C` and `delta_degsC`
  weren't defined. They now are.

### Documentation

- README and API docs rewritten to be easier to follow, with the rules
  for `CFContext` (one block per variable, convert inside the block) and
  the common pitfalls.
- Documented what happens without `units_metadata`: pint uses the
  UDUNITS-2 rule (`degC` is a temperature, `degC/s` a difference), and
  `cf_attributes_for` reports that guess. Keep the original attribute when
  writing such data back.
- Documented that `ureg("2 degC/s")` gives 275.15 K/s, not 2 K/s: read CF
  data with `ureg.Quantity(values, units)`.

### Internal

- `cf_string_to_pint` only translates syntax now. A separate preprocessor
  applies `CFContext`. No change for users.

## v0.2.1

- Added `THIRD_PARTY_LICENSES.md` and the UDUNITS-2 copyright notice,
  which its license requires us to ship (needed for conda-forge).
- Fixed the registry generator in `tools/` (`xmlrd.py`), which broke when
  `cf_string_to_pint` started rejecting `K @ 273.15`. No change for users.

## v0.2.0

### New

- CF units that UDUNITS-2 doesn't define, on by default (#10). Turn them
  off with `cf_unitregistry(cf_extensions=False)`:
  - `level`, `sigma_level`, `layer`, kept for old COARDS files. They warn
    when used.
  - `practical_salinity_unit` / `psu`, equal to `1e-3`.
  - `decibel` / `dB`, `bel`, as plain dimensionless ratios.
  - `Sv` now means sverdrup, not sievert. `rem` still means centisievert.
- `CFContext`, to read CF's `units_metadata` temperature attribute (#9).
  With `"temperature: difference"`, `degC` becomes `delta_degC`.
- `cf_attributes_for`, the reverse: works out `units_metadata` from a unit
  when writing a result. It returns `{}` for a non-temperature unit, and
  `"temperature: unknown"` for kelvin and Rankine, where the unit alone
  can't tell.

### Fixes

- `CFContext` with `"temperature: difference"`: `degree_C**1` was read as
  a temperature, and `(degree_C)` produced an invalid unit.
- A shifted unit (`K @ 273.15`) failed with an unrelated pint error. It now
  raises a clear `NotImplementedError`.
- [Temperature aliases](https://github.com/hgrecco/pint/issues/2296) were
  defined wrongly.
- Unit syntax now matches the UDUNITS-2 parser: `Per` works in any case,
  malformed superscripts (`m²⁻`) are rejected, and `lg(re ...)` requires
  `re`.
- `footcandle` had a wrong conversion factor (UDUNITS-2 files resynced).

### Internal

- Removed dead code in the timestamp grammar, `CFFormatter` and
  `tools/xmlrd.py`, and made `tools/xmlrd.py` more robust.

## v0.1.1 (2026-04-08)

Initial release
