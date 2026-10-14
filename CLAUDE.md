# pint-cf

A Pint unit registry and formatter for CF/UDUNITS-2 unit strings. Users are
scientists reading and writing NetCDF/CF data: a silently wrong number is the
worst possible bug here, worse than an exception.

## Correctness rules

- **The CF conventions come first.** Follow the latest released version
  (currently CF 1.13). Quote the section when a behavior depends on it.
  Relevant sections: 3.1, 3.1.1–3.1.3, 3.3, 4.1–4.4, 7.5.3 and Appendix E.
- **Without `CFContext`, behave like UDUNITS-2.** The reference
  implementations are UDUNITS-2 itself, `cf_units` (its Python wrapper) and
  `cfunits`. Where they disagree with CF, CF wins; document the divergence.
- **Don't attribute to CF what it doesn't say.** Keep CF requirements apart
  from UDUNITS conventions, in code comments and docs too. Example
  (section 3.1.2): without `units_metadata`, CF says to assume
  `temperature: unknown`, for which "a correct conversion cannot be
  guaranteed". Reading a bare unit as on-scale and a compound one as a
  difference is UDUNITS' assumption, which CF quotes as guidance only. CF
  doesn't require it.
- **Be physically correct.** Check conversions against UDUNITS (through
  `cf_units`) before trusting them, not just against pint.
- **Never silently override an explicit choice by the user** (an argument, a
  `units_metadata` value). Honor it, or raise an error explaining why it
  can't be honored.

## Unit inventory

- **UDUNITS-2 XML is the source of truth.** The registry files in
  `src/pint_cf/resources/registry/udunits2-*.txt` are generated from
  `tools/xml/*.xml`, taken from the UDUNITS-2 GitHub master, by
  `tools/parse_xml.py`. Don't edit them by hand; regenerate them.
- **CF-only units are loaded explicitly**, not mixed into the generated
  files:
  - `cf-coards-vertical.txt`: `level`, `sigma_level`, `layer`. CF allows
    them unconditionally, so they're always loaded and warn with
    `CFDeprecatedUnitWarning`.
  - `cf-extensions.txt`: community additions taken from `cfunits`/`cf-units`
    and the CF FAQ (`psu`, `Sv` as sverdrup, ...). They're optional and can
    be turned off with `cf_unitregistry(cf_extensions=False)`.
- **Don't invent units.** Every unit must come from UDUNITS-2, the CF
  conventions/FAQ, or `cfunits`/`cf-units`. Cite the source in the
  definition file.
- **Decibels:** pending on the `decibel` branch. The target is a logarithmic
  `dB` as in UDUNITS master and the CF FAQ, replacing the linear `decibel = 1`
  from `cfunits`. Don't change logarithmic units on other branches.

## Design constraints

- **Non-intrusive:** don't subclass pint's `UnitRegistry`, `Unit` or
  `Quantity`. pint-cf only adds preprocessors, definitions and a formatter.
- **`cf_string_to_pint` (`parser.py`) is a pure syntax translation**, from
  UDUNITS-2 to pint. It must not depend on a registry or on `CFContext`.
- **Temperature `units_metadata`** is applied by a separate preprocessor
  (`context._make_temperature_preprocessor`), chained after
  `cf_string_to_pint`.
  - Inside a preprocessor, never call a registry method that takes a unit
    string. Since pint 0.26, those methods apply the preprocessors again and
    recurse. `parse_unit_name`, `get_name` and
    `_get_dimensionality(UnitsContainer)` are safe.
  - The `CFContext` contract: one block holds one variable. The metadata
    applies to every temperature unit read inside the block, including the
    target of a `.to()`. See the `CFContext` docstring and the README.
- **Supported pint versions:** `Pint>=0.25.2` up to the latest release. Test
  both ends when touching pint internals; private imports may need a
  fallback.

## Tests

- `uv sync`, then `uv run pytest`. Lint and format run through pre-commit
  hooks (`uv run prek run --all-files`).
- **Tests must not depend on `cf_units` or `cfunits`.** CI installs only the
  `tests` dependency group. Use those libraries in `tools/` scripts that
  generate expected values, and store the values in `tests/data/`. Examples:
  `tools/write_canonical_units.py`, `tools/write_udunits_conversions.py`.
- **`tests/test_cf_conformance.py` holds one section per CF section**, each
  quoting the requirement it checks. Every CF-related behavior change needs a
  test there.
- **Known violations are `xfail(strict=True)`**, with the
  `CODE_REVIEW.md` finding number in the reason, so the test reports an
  `XPASS` once the finding is fixed. Remove the mark when fixing.
- Prefer parametrized tables of cases over repeated test functions.

## Workflow

- **Don't modify `.github/workflows/`.** CI is maintained by a collaborator,
  so propose changes instead.
- **No AI attribution in commits or PRs:** no `Co-Authored-By` or
  "Generated with" lines.
- Keep `CHANGELOG.md` up to date with user-visible changes.
- `CODE_REVIEW.md` is a local, untracked working document. Don't commit it.
