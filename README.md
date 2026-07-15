# pint-cf

`pint-cf` is a lightweight, pure-Python package that extends Pint with a
CF-compliant unit registry and formatter.

## Features

- A CF-compliant Pint `UnitRegistry` that understands UDUNITS-2 unit strings.
- A `cf` format for `Unit`/`Quantity` that writes results back out as CF strings.
- `CFContext`, which correctly reads CF's `units_metadata` temperature
  attribute and resolves decibel reference levels from `standard_name`.
- CF units that UDUNITS-2 itself doesn't define (`level`, `psu`, `decibel`,
  `sverdrup`'s `Sv` symbol, ...), included by default.

## Notes

- No support for **time coordinates** (e.g. `days since 2001-01-01`) or
  **climate calendars** (e.g. `360_day`) - Pint has no notion of a time
  origin or calendar, so it can't represent these as units. Use
  [cftime](https://unidata.github.io/cftime/) for those instead.
- `decibel`/`bel` are plain dimensionless ratio units by default, with no
  physical reference level attached - see "Decibel `standard_name`" below
  for resolving one from the variable's `standard_name` instead.

## Installation

Install via `pip`:

```bash
pip install pint-cf
```

or via `conda`, from conda-forge:

```bash
conda install conda-forge::pint-cf
```

## Usage

Create a CF-ready unit registry with `cf_unitregistry()`. This returns a
plain `pint.UnitRegistry` instance with the CF/UDUNITS-2 unit definitions
already loaded, so it behaves exactly like any other Pint registry. This
also registers the `cf` format.

```python
from pint_cf import cf_unitregistry

ureg = cf_unitregistry()

q = ureg("10 meters per second^2").to("km s-2")

print(f"{q:cf}")  # 0.01 kilometer-second^-2
print(f"{q:~cf}")  # 0.01 km/s2
```

### Temperature `units_metadata`

CF distinguishes an on-scale temperature (e.g. today's temperature) from a
temperature *difference* (e.g. an anomaly) with a `units_metadata`
attribute - the plain `units` string alone can't tell them apart.

When reading a variable that has this attribute, wrap the value in
`CFContext`:

```python
from pint_cf import cf_unitregistry, CFContext

ureg = cf_unitregistry()

with CFContext(units_metadata="temperature: difference"):
    q = ureg.Quantity(1, "degree_C")

print(q.units)  # delta_degree_Celsius
```

Without `CFContext` (or with `units_metadata` absent), nothing changes - an
on-scale temperature is read as usual.

When writing a result back out, `cf_attributes_for` does the reverse: it
derives the `units_metadata` attribute from an already-computed `Unit` or
`Quantity`, ready to merge into a NetCDF variable's attributes:

```python
from pint_cf import cf_attributes_for

print(cf_attributes_for(q))  # {"units_metadata": "temperature: difference"}
print(cf_attributes_for(ureg.Unit("meter")))  # {} - not a temperature unit

ds[name].attrs.update(cf_attributes_for(q.units))
```

This round-trips exactly for Celsius and Fahrenheit. Kelvin and Rankine
have no zero-offset, so on-scale and difference look identical for them -
`cf_attributes_for` reports `"temperature: unknown"` rather than guessing.

### CF units not in UDUNITS-2

CF defines a few units that UDUNITS-2 doesn't, sourced from
[`cfunits`](https://ncas-cms.github.io/cfunits/cfunits.Units.html#cfunits-units). `cf_unitregistry()`
includes them by default:

| Unit                                 | Behavior                                                                                                              |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `level`, `sigma_level`, `layer`       | Dimensionless; kept only for legacy COARDS files, so using one raises a `DeprecationWarning`.                          |
| `practical_salinity_unit` / `psu`     | `1e-3`, not `1` (CF's own FAQ is out of date here).                                                                    |
| `decibel` / `dB`, `bel`               | Plain dimensionless ratio units by default (see "Decibel `standard_name`" below).                                     |
| `sverdrup` / `Sv`                     | `Sv` now means `sverdrup` (ocean volume transport), not `sievert` - `sievert` itself still works by its full name.     |

Pass `cf_extensions=False` to `cf_unitregistry()` for a registry that
matches plain UDUNITS-2 instead, without any of these additions - including
`dB`/`decibel`/`bel` themselves, so the `standard_name` resolution below
doesn't apply either.

#### Decibel `standard_name`

A `dB`/`decibel` value's physical reference level isn't in the unit string
either - CF's own FAQ says it "is specified in the standard names that use
this canonical unit". `decibel`/`bel` are plain dimensionless ratio units
by default, with no physical reference level attached, matching the
convention used by [`cfunits`](https://github.com/NCAS-CMS/cfunits) and
[`cf-units`](https://github.com/SciTools/cf-units). `CFContext` also
accepts `standard_name` to resolve this instead: passing the variable's
`standard_name` resolves a bare `dB` to the correct reference level and
dimension, for one of the four CF standard names that use dB as their
canonical unit:

```python
from pint_cf import cf_unitregistry, CFContext

ureg = cf_unitregistry()

with CFContext(standard_name="sound_pressure_level_in_air"):
    q = ureg.Quantity(74, "dB")

print(q.to("pascal"))  # 0.10023744672545465 pascal
print(f"{q:~cf}")  # 74 dB - still writes back out as a plain CF dB value
```

Without `CFContext` (or with any other `standard_name`), `dB`/`decibel`
stays the plain dimensionless ratio unit. `bel` isn't covered - CF's
standard name table only ever pairs these standard names with `dB`.

`cf_attributes_for` does the reverse here too, deriving `standard_name`
from an already-resolved quantity:

```python
from pint_cf import cf_attributes_for

print(cf_attributes_for(q))  # {"standard_name": "sound_pressure_level_in_air"}
```

Internally, a resolved unit (`q.units`) is a private, leading-underscore
pint unit (e.g. `_dB_sound_pressure_level_in_air`) - pint-cf's own
invention to carry the reference level, since CF's table only names the
canonical `dB` unit, not a pint-parseable one with that reference built
in. Never type one of these directly; they exist only so `CFContext` and
`cf_attributes_for` have something to resolve to and read back from, and
only under `cf_extensions=True` (the default) - with `cf_extensions=False`
neither the private unit nor plain `dB` is defined, so resolving a
`standard_name` raises `UndefinedUnitError`.

## Third-party notices

The UDUNITS-2 unit database this package is built on is redistributed
under its own license - see
[THIRD_PARTY_LICENSES.md](https://github.com/pgamez/pint-cf/blob/main/THIRD_PARTY_LICENSES.md).
