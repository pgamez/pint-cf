# pint-cf

This package extends Pint with a CF-compliant unit registry and formatter.

## Features

- A CF-compliant Pint `UnitRegistry`, understanding UDUNITS-2 unit strings.
- A `cf` format for `Unit`/`Quantity`, to write results back out as CF strings.
- `CFContext`, to correctly read CF's `units_metadata` temperature attribute.
- CF units that UDUNITS-2 itself doesn't define (`level`, `psu`, `decibel`,
  `sverdrup`'s `Sv` symbol, ...), included by default.

Known limitations:

- No support for **time coordinates** (e.g. `days since 2001-01-01`) or
  **climate calendars** (e.g. `360_day`). Use
  [cftime](https://unidata.github.io/cftime/) for those instead.
- `decibel`/`bel` are treated as plain dimensionless ratio units, matching
  [`cfunits`](https://github.com/NCAS-CMS/cfunits)/`cf-units` - CF's own
  reference level for a `dB` value depends on the variable's
  `standard_name`, but neither of those reference packages resolves it
  either, so pint-cf follows the same convention rather than the letter of
  the spec.

## Installation

Install via `pip`:

```bash
pip install pint-cf
```

## Usage

Create a CF-ready unit registry with `cf_unitregistry()`. This also
registers the `cf` format.

```python
from pint_cf import cf_unitregistry

ureg = cf_unitregistry()

q = ureg('10 meters per second^2').to('km s-2')

print(f"{q:cf}")   # 0.01 kilometer-second^-2
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

print(cf_attributes_for(q))                   # {"units_metadata": "temperature: difference"}
print(cf_attributes_for(ureg.Unit("meter")))  # {} - not a temperature unit

ds[name].attrs.update(cf_attributes_for(q.units))
```

This round-trips exactly for Celsius and Fahrenheit. Kelvin and Rankine
have no zero-offset, so on-scale and difference look identical for them -
`cf_attributes_for` reports `"temperature: unknown"` rather than guessing.

### CF units not in UDUNITS-2

CF defines a few units that UDUNITS-2 doesn't
([details](https://github.com/pgamez/pint-cf/issues/10)), sourced from
[`cfunits`](https://github.com/NCAS-CMS/cfunits). `cf_unitregistry()`
includes them by default:

| Unit                                 | Behavior                                                                                                              |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `level`, `sigma_level`, `layer`       | Dimensionless; kept only for legacy COARDS files, so using one raises a `DeprecationWarning`.                          |
| `practical_salinity_unit` / `psu`     | `1e-3`, not `1` (CF's own FAQ is out of date here).                                                                    |
| `decibel` / `dB`, `bel`               | Plain dimensionless ratio units (see "Known limitations" above).                                                       |
| `sverdrup` / `Sv`                     | `Sv` now means `sverdrup` (ocean volume transport), not `sievert` - `sievert` itself still works by its full name.     |

Pass `cf_extensions=False` to `cf_unitregistry()` for a registry that
matches plain UDUNITS-2 instead, without any of these additions.
