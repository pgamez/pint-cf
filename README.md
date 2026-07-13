# pint-cf

This package extends Pint with a CF-compliant unit registry and formatter.

**EXPERIMENTAL PACKAGE**

## Features

This package provides:

- A CF-compliant Pint UnitRegistry with explicit plural aliases.
- A custom `cf` formatter that supports both long-name and short-symbol formats.
- `CFContext`, for CF's `units_metadata` temperature attribute (CF-1.11).

Known limitations:

- Pint does not support **time coordinates** (e.g.
  `days since 2001-01-01`) or **climate calendars** (e.g., `360_days`).
  Consider using [cftime](https://unidata.github.io/cftime/) instead.
- CF units not supported by UDUNITS2 are not handled yet

<!-- - Pint does not support **scaling factors** in unit expressions, such as
  `1.5 * pint.Unit('0.1 m')`. You can work around this by adding your own
  [unit definition](https://pint.readthedocs.io/en/stable/advanced/defining.html#programmatically). -->

## Installation

Install via `pip`:

```bash
pip install pint-cf
```

## Usage

Create a CF-ready unit registry with `cf_unitregistry()`.
This function also registers the `cf` formatter.

```python
from pint_cf import cf_unitregistry

ureg = cf_unitregistry()
print(type(ureg))  # <class 'pint.registry.UnitRegistry'>

q = ureg('10 meters per second^2').to('km s-2')

print(f"{q:cf}")   # 0.01 kilometer-second^-2
print(f"{q:~cf}")  # 0.01 km/s2
```

### CF `units_metadata` (temperature)

CF-1.11 introduced `units_metadata` to distinguish an on-scale temperature
from a temperature difference (e.g. an anomaly), since the plain `units`
attribute alone is ambiguous - see the CF conventions, section 3.1.2. Wrap a
unit/quantity construction in `CFContext` when you have that attribute
available (e.g. reading a NetCDF variable):

```python
from pint_cf import cf_unitregistry, CFContext

ureg = cf_unitregistry()

with CFContext(units_metadata="temperature: difference"):
    q = ureg.Quantity(1, "degree_C")

print(q.units)  # delta_degree_Celsius
```

With `units_metadata` absent or `"temperature: unknown"`, nothing changes:
pint already applies UDUNITS' own heuristic (a temperature unit combined
with, or raised to a power other than, another unit becomes a `delta_` unit
automatically). `CFContext` only matters to force `"temperature: difference"`
onto a bare unit that would otherwise be read as on-scale. Forcing
`"temperature: on_scale"` onto a compound expression isn't supported through
`CFContext` - call `ureg.Quantity(value, units, as_delta=False)` directly for
that rare case.

To write a result back out, `cf_attributes_for` derives the CF variable
attributes from an already-computed Unit or Quantity - the reverse
direction. It returns a dict, ready to merge straight into a NetCDF
variable's attributes:

```python
from pint_cf import cf_attributes_for

print(cf_attributes_for(q))          # {"units_metadata": "temperature: difference"}
print(cf_attributes_for(q.units))    # same, also accepts a bare Unit
print(cf_attributes_for(ureg.Unit("meter")))  # {} - not a temperature unit

ds[name].attrs.update(cf_attributes_for(q.units))
```

The `units_metadata` entry is only reliable for units with a genuine
on_scale/difference distinction (Celsius, Fahrenheit). Kelvin and Rankine
have no offset, so they have no `delta_` counterpart either - on_scale and
difference are numerically identical for them, and `cf_attributes_for`
reports `"temperature: unknown"` rather than guessing. If that distinction
matters for your data, track it through your own computation instead of
trying to recover it from the resulting unit.
