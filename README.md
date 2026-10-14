# pint-cf

`pint-cf` extends [Pint](https://pint.readthedocs.io) so it reads and writes
the unit strings used in NetCDF files that follow the
[CF conventions](https://cfconventions.org) (the UDUNITS-2 syntax).

- `cf_unitregistry()`: a Pint registry that understands strings like
  `m s-2` or `kg m-2 s-1`.
- `"cf"` format: writes a Pint unit back as a CF string.
- `CFContext`: reads the `units_metadata` attribute of temperatures.
- `cf_attributes_for`: works out `units_metadata` when writing a result.

## Installation

```bash
pip install pint-cf
# or
conda install conda-forge::pint-cf
```

## Quick start

```python
from pint_cf import cf_unitregistry

ureg = cf_unitregistry()

q = ureg.Quantity(10, "m s-2").to("km s-2")

print(f"{q:cf}")   # 0.01 kilometer-second^-2
print(f"{q:~cf}")  # 0.01 km/s2
```

Use `ureg` as any Pint registry. Format with `cf` (full names) or `~cf`
(symbols) to get a string you can store in a `units` attribute.

## Temperatures

### The problem

A `units` attribute of `degC` doesn't say whether the data is a
temperature (15 °C) or a temperature difference (a warming of 5 °C). The
two convert differently:

| Data | In °F |
| -------------------- | ------------- |
| 15 °C (temperature) | 59 °F |
| 5 °C (difference) | 9 °F |

CF 1.13 (section 3.1.2) adds a `units_metadata` attribute to tell them
apart: `"temperature: on_scale"`, `"temperature: difference"` or
`"temperature: unknown"`.

### Reading a variable: `CFContext`

Pass the variable's `units_metadata` to `CFContext`, and read **and
convert** the variable inside the block:

```python
from pint_cf import CFContext

with CFContext(units_metadata="temperature: difference"):
    anomaly = ureg.Quantity(5, "degC")  # 5 delta_degree_Celsius
    anomaly.to("degF")                  # 9 delta_fahrenheit
```

Three rules:

1. **One block, one variable.** Everything read inside the block gets its
   metadata, including the target of `.to()`.
1. **Convert inside the block.** This matters for kelvin and Rankine (see
   below).
1. **No attribute: `None`.** For a variable without `units_metadata`, use
   `CFContext(units_metadata=None)`, which CF reads as
   `"temperature: unknown"`. It's a different variable, so it doesn't take
   the metadata of an outer block.

A `units_metadata` on a unit that isn't a temperature is ignored (CF
forbids it there).

With xarray, use one block per variable, never one block around the whole
dataset:

```python
ureg.force_ndarray_like = True  # required by pint-xarray

quantified = {}
for name, var in ds.data_vars.items():
    with CFContext(units_metadata=var.attrs.get("units_metadata")):
        quantified[name] = ds[[name]].pint.quantify(unit_registry=ureg)[name]
```

### Why convert inside the block

Pint stores a Celsius or Fahrenheit difference as a separate unit
(`delta_degC`), so the quantity remembers it's a difference. Kelvin and
Rankine have no `delta_` unit in Pint: a kelvin is just a kelvin.
Outside the block, Pint decides by the target unit, and a bare `"degF"`
means a temperature:

```python
with CFContext(units_metadata="temperature: difference"):
    k = ureg.Quantity(1, "K")
    c = ureg.Quantity(1, "degC")
    k.to("degF")   # 1.8 delta_fahrenheit   correct

k.to("degF")       # -457.87 fahrenheit     wrong, no error
c.to("degF")       # DimensionalityError    safe: c is still a difference
```

### Without `units_metadata`

CF says to treat it as `"temperature: unknown"`: a correct conversion
can't be guaranteed. pint-cf then leaves Pint's default rule, which is
the one UDUNITS-2 uses (CF quotes it as guidance only):

- a bare unit (`degC`) is a temperature: `15 degC` → `288.15 K`;
- a compound unit (`degC/s`, `degC2`) is a difference: `2 degC/s` →
  `2 K/s`.

### Writing a result: `cf_attributes_for`

```python
from pint_cf import cf_attributes_for

cf_attributes_for(anomaly)            # {'units_metadata': 'temperature: difference'}
cf_attributes_for(ureg.Unit("m"))     # {}  (not a temperature)

ds[name].attrs.update(cf_attributes_for(result))
```

It reports what Pint knows about the unit, so:

- For kelvin and Rankine it returns `"temperature: unknown"`: the unit
  alone can't tell.
- If the input had no `units_metadata` (or `unknown`), the answer is only
  Pint's guess. Keep the original attribute, unless your computation
  settled it (subtracting two temperatures gives a difference).

### Pitfalls

1. Putting the value inside the string: `ureg("2 degC/s")`.
1. An on-scale temperature inside a compound unit, such as
   `kg degC m-2`: it can't be converted from the units alone.

#### 1. Value inside the string

`ureg("2 degC/s")` isn't a CF units string but an arithmetic expression,
`(2 * degC) / s`: a temperature of 2 °C divided by seconds. The pint-cf
registry turns on Pint's `autoconvert_offset_to_baseunit`, so arithmetic
with a temperature uses kelvin, as physics requires. 275.15 K/s is right
for that expression, but it isn't what the CF units `degC/s` mean.

```python
ureg.Quantity(2, "degC/s").to("K/s")  # 2 K/s       (as UDUNITS-2)
ureg("2 degC/s").to("K/s")            # 275.15 K/s  (2 °C = 275.15 K, / s)
```

Pass the value apart from the units: `ureg.Quantity(values, units)`.

#### 2. On-scale temperature in a compound unit

CF 1.13 (section 3.1.2) says the units alone aren't enough to convert it:

> If the quantity is an on-scale temperature multiplied by some other
> quantity, it is not possible to convert the data from the units given
> to any other units that involve a temperature with a different origin,
> given only the units. For instance, when temperature is on-scale, a
> value in kg degree_C m-2 can be converted to a value in kg K m-2 only
> if we know separately the values in degree_C and kg m-2 of which it is
> the product.

For example, `10 kg degC m-2` may be 1 °C × 10 kg m-2 (2741.5 kg K m-2)
or 10 °C × 1 kg m-2 (283.15 kg K m-2).

Pint doesn't support such a unit either. What you get depends on how you
reach it:

- **Without metadata**, `kg degC m-2` is read as a difference (the
  UDUNITS-2 rule above), so there's no on-scale unit at all.
- **With `CFContext(units_metadata="temperature: on_scale")`**, pint-cf
  raises `ValueError`. CF doesn't ask for an error: that's pint-cf's
  choice, rather than give a wrong number.
- **Built by hand**, with `as_delta=False` or by multiplying units, Pint
  converts it to meaningless numbers, without an error.
  pint-cf can't block this from outside Pint, so don't do it.

```python
ureg.Quantity(10, "kg degC m-2").to("kg K m-2")  # 10 kg K m-2 (difference)

with CFContext(units_metadata="temperature: on_scale"):
    ureg.Quantity(10, "kg degC m-2")             # ValueError

u = ureg.parse_units
q = ureg.Quantity(10, u("kg degC m-2", as_delta=False))  # or Unit("degC") * Unit("kg m-2")
q.to(u("g degC m-2", as_delta=False))   # 10, should be 10000
q.to(u("kg degF m-2", as_delta=False))  # 50, CF says it can't be converted
```

**The solution.** CF only allows the conversion if you know the
temperature and the rest separately. If you do, multiply them as
quantities:

```python
q = ureg.Quantity(10, "degC") * ureg.Quantity(1, "kg m-2")
q.to("kg K m-2")  # 283.15 kg K m-2
```

If the file only has the product, pint-cf can't read it as on-scale.
That includes conversions CF would allow because the temperature origin
doesn't change, such as `kg degC m-2` → `g degC m-2`.

## Units not in UDUNITS-2

pint-cf adds these units by default:

| Unit | Notes |
| --------------------------------- | ----------------------------------------------------------- |
| `practical_salinity_unit` / `psu` | Equal to `1e-3`, not `1` (the CF FAQ is out of date here). |
| `decibel` / `dB`, `bel` | Plain dimensionless ratios, with no reference level, as in `cfunits` and `cf-units`. |
| `sverdrup` / `Sv` | `Sv` is the sverdrup (ocean transport). Write `sievert` in full. |

`cf_unitregistry(cf_extensions=False)` leaves them out, for a registry
that matches plain UDUNITS-2.

`level`, `sigma_level` and `layer` are always defined, since CF allows
them for old COARDS files. Using one warns with
`pint_cf.CFDeprecatedUnitWarning`, because CF recommends a dimensionless
vertical coordinate instead. Support for them isn't going away.

## Not supported

- **Time coordinates** (`days since 2001-01-01`) and **calendars**
  (`360_day`): Pint has no time origin or calendar. Use
  [cftime](https://unidata.github.io/cftime/).

## Third-party notices

The UDUNITS-2 unit database this package is built on is redistributed
under its own license: see
[THIRD_PARTY_LICENSES.md](https://github.com/pgamez/pint-cf/blob/main/THIRD_PARTY_LICENSES.md).
