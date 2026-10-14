# pint-cf

`pint-cf` is a lightweight, pure-Python package that extends Pint with a
CF-compliant unit registry and formatter.

## Features

- A CF-compliant Pint `UnitRegistry` that understands UDUNITS-2 unit strings.
- A `cf` format for `Unit`/`Quantity` that writes results back out as CF strings.
- `CFContext`, which correctly reads CF's `units_metadata` temperature attribute.
- CF units that UDUNITS-2 itself doesn't define (`level`, `psu`, `decibel`,
  `sverdrup`'s `Sv` symbol, ...), included by default.

## Notes

- No support for **time coordinates** (e.g. `days since 2001-01-01`) or
  **climate calendars** (e.g. `360_day`) - Pint has no notion of a time
  origin or calendar, so it can't represent these as units. Use
  [cftime](https://unidata.github.io/cftime/) for those instead.
- `decibel`/`bel` are treated as plain dimensionless ratio units, with no
  physical reference level attached, matching the convention used by
  [`cfunits`](https://github.com/NCAS-CMS/cfunits) and
  [`cf-units`](https://github.com/SciTools/cf-units).

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

Create a CF-ready unit registry with `cf_unitregistry()`. This also
registers the `cf` format.

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

The metadata applies to every temperature unit read inside the block,
including the target of a conversion and any unit read by code you call
from inside it. Keep one variable per block: read it there and convert it
there too. Anything belonging to a variable with different metadata goes
outside. A variable without `units_metadata` gets
`CFContext(units_metadata=None)`, which CF reads as `"temperature: unknown"`
and which doesn't inherit an outer block's metadata.

With xarray, quantify one variable per block. Calling `ds.pint.quantify()`
on the whole dataset inside a single block would give every temperature
variable the same metadata:

```python
ureg.force_ndarray_like = True  # required by pint-xarray

quantified = {}
for name, var in ds.data_vars.items():
    with CFContext(units_metadata=var.attrs.get("units_metadata")):
        quantified[name] = ds[[name]].pint.quantify(unit_registry=ureg)[name]
```

Convert inside the block whatever the unit. Celsius and Fahrenheit keep a
difference as a `delta_` unit, but kelvin and Rankine have no offset: pint
stores on-scale and difference as the same unit, so the metadata can't
travel with the quantity:

```python
with CFContext(units_metadata="temperature: difference"):
    anomaly = ureg.Quantity(1, "K")
    anomaly.to("degF")  # 1.8 delta_fahrenheit

anomaly.to("degF")      # -457.87 degF: outside, "degF" has no metadata,
                        # so pint reads it as on-scale
```

A `units_metadata` on a non-temperature unit, which CF forbids, is ignored.

Without `CFContext`, with `units_metadata` absent, or with
`"temperature: unknown"`, CF says the data is ambiguous. In that case pint
applies the UDUNITS rule, which CF quotes as guidance only: a bare unit
(`degC`) is read as on-scale, and a unit raised to a power or combined with
others (`degC/s`, `degC2`) as a difference.

`"temperature: on_scale"` on a compound unit that contains a Celsius or
Fahrenheit temperature (e.g. `kg degC m-2`) is valid CF, but `CFContext`
raises `ValueError` for it: pint has no safe way to represent it. As CF
notes, such values can only be converted when the on-scale temperature and
the other factors are known separately. If they are, multiply them as
quantities, and pint converts the temperature to kelvin first:

```python
q = ureg.Quantity(10, "degC") * ureg.Quantity(1, "kg m-2")
q.to("kg K m-2")  # 283.15 kg K m-2
```

Don't use `ureg.parse_units(units, as_delta=False)` to force an on-scale
compound unit: pint (0.25 and 0.26) converts such units wrongly without any
error.

When writing a result back out, `cf_attributes_for` does the reverse: it
derives the `units_metadata` attribute from an already-computed `Unit` or
`Quantity`, ready to merge into a NetCDF variable's attributes:

```python
from pint_cf import cf_attributes_for

print(cf_attributes_for(q))  # {"units_metadata": "temperature: difference"}
print(cf_attributes_for(ureg.Unit("meter")))  # {} - not a temperature unit

ds[name].attrs.update(cf_attributes_for(q.units))
```

This round-trips exactly for Celsius and Fahrenheit read with an explicit
`"temperature: on_scale"` or `"temperature: difference"`. Kelvin and
Rankine have no zero-offset, so on-scale and difference look identical for
them - `cf_attributes_for` reports `"temperature: unknown"` rather than
guessing.

`cf_attributes_for` reports how pint interprets the unit, not the metadata
it was read with - a pint unit can't carry "unknown". If the input's
`units_metadata` was `"temperature: unknown"` or absent, it reports the
UDUNITS guess above as if it were known. In that case keep the original
attribute instead, unless your computation settled the question (e.g.
subtracting two on-scale temperatures gives a difference).

### CF units not in UDUNITS-2

`level`, `sigma_level`, `layer` are dimensionless vertical-coordinate
placeholders kept for legacy COARDS files - the CF conventions allow them
unconditionally, so `cf_unitregistry()` always defines them, regardless of
`cf_extensions`. Using one raises a `pint_cf.CFDeprecatedUnitWarning` (a
`UserWarning` subclass, not `DeprecationWarning`/`FutureWarning`: pint-cf
isn't planning to remove support for these strings, it's just flagging
that CF itself calls this use deprecated in favor of a proper
dimensionless vertical coordinate variable).

CF also defines a few more units that UDUNITS-2 doesn't, sourced from
[`cfunits`](https://ncas-cms.github.io/cfunits/cfunits.Units.html#cfunits-units). `cf_unitregistry()`
includes these by default too:

| Unit | Behavior |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `practical_salinity_unit` / `psu` | `1e-3`, not `1` (CF's own FAQ is out of date here). |
| `decibel` / `dB`, `bel` | Plain dimensionless ratio units (see "Notes" above). |
| `sverdrup` / `Sv` | `Sv` now means `sverdrup` (ocean volume transport), not `sievert` - `sievert` itself still works by its full name. |

Pass `cf_extensions=False` to `cf_unitregistry()` for a registry that
matches plain UDUNITS-2 instead, without these additions (the
`level`/`sigma_level`/`layer` placeholders are still defined).

## Third-party notices

The UDUNITS-2 unit database this package is built on is redistributed
under its own license - see
[THIRD_PARTY_LICENSES.md](https://github.com/pgamez/pint-cf/blob/main/THIRD_PARTY_LICENSES.md).
