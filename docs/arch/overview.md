# Package overview

pint-cf doesn't subclass anything from pint. It builds a normal
`pint.UnitRegistry` and adds three things to it: unit definitions,
preprocessors (which rewrite a unit string before pint parses it), and a
formatter.

## Public API

| Symbol | What it does |
| ------------------------- | ------------------------------------------------------------------- |
| `cf_unitregistry()` | Builds the registry. Entry point. |
| `CFContext` | Context manager: applies a `units_metadata` while reading units. |
| `cf_attributes_for()` | Works out `units_metadata` from a unit, for writing. |
| `CFDeprecatedUnitWarning` | Warning for `level`, `sigma_level`, `layer`. Exported for filtering. |

## Modules

| File | Contents |
| ---------------------- | ----------------------------------------------------------------------- |
| `units.py` | `cf_unitregistry()`, the `cf` formatter, the deprecated-unit warning. |
| `parser.py` | `cf_string_to_pint()`: UDUNITS-2 syntax → pint syntax (Lark grammar). |
| `context.py` | `CFContext`, the temperature preprocessor, `cf_attributes_for()`. |
| `resources/registry/` | Unit definition files (see below). |

![pint-cf structure](structure.png)

## How a unit string is read

`cf_unitregistry()` sets up three preprocessors. pint runs them in order on
every unit string, before parsing it:

1. `_warn_if_deprecated_cf_unit`: warns on `level`, `sigma_level`,
   `layer`. Doesn't change the string.
1. `cf_string_to_pint`: translates the syntax, e.g. `m s-2` → `m * s ** -2`.
   Pure translation: it doesn't know about the registry or `CFContext`.
1. The temperature preprocessor (`context._make_temperature_preprocessor`):
   if a `CFContext` is active, turns `degC` into `delta_degC` for
   `"temperature: difference"`, or rejects what pint can't represent. It
   needs the registry, so it's added after the registry is created.

Two details:

- `CFContext` stores the metadata in a `ContextVar`. The temperature
  preprocessor reads it. `cf_attributes_for()` doesn't: it only looks at
  the unit.
- pint's `parse_unit` cache is turned off (`_NoCache`). It's keyed on the
  string before preprocessing, so the same string read in two different
  `CFContext` blocks would get the first result. Turning it off costs
  nothing measurable.

Writing goes through `CFFormatter` (the `cf` and `~cf` formats), which
turns a pint unit back into a CF string. It drops `delta_` and `Δ`, since
CF puts that information in `units_metadata` instead.

![Usage workflow with pint-cf](sd-usage.png)

![Temperature units_metadata round-trip](sd-temperature.png)

## Unit definition files

All in `src/pint_cf/resources/registry/`:

| File | Source | Loaded |
| -------------------------- | ---------------------------------------- | ----------------- |
| `udunits2*.txt` | Generated from the UDUNITS-2 XML | Always |
| `cf-coards-vertical.txt` | CF: `level`, `sigma_level`, `layer` | Always |
| `cf-extensions.txt` | `cfunits`: `psu`, `dB`, `Sv` as sverdrup | Unless `cf_extensions=False` |

The `udunits2*.txt` files are generated. Don't edit them by hand:

1. Update `tools/xml/*.xml` from UDUNITS-2 on GitHub.
1. Run `tools/parse_xml.py`. It uses `tools/xmlrd.py`, which builds each
   definition with `cf_string_to_pint()` (the same translation the
   package uses at runtime) and keeps the XML comments.
1. Move the output to `src/pint_cf/resources/registry/`.

The two `cf-*.txt` files are written by hand, with the source of each unit
in a comment.

![Registry file generation](sd-registry.png)

## Expected values for tests

Tests don't depend on `cf_units` or `cfunits`. These scripts use them to
compute expected values once and store them in `tests/data/`:

| Script | Writes |
| ------------------------------------- | --------------------------------- |
| `tools/write_udunits_conversions.py` | `udunits_conversions.tsv`: conversions computed by UDUNITS-2. |
| `tools/write_canonical_units.py` | `cf_canonical_units_written.tsv`: how pint-cf writes each CF canonical unit. |

Review the diff of the generated file before committing it.
