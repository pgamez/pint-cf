# To-do and discussions

## Short-term tasks

- [DONE] Fix `delta_` prefixes for temperature aliases in the UnitRegistry
- [IN-PROGRESS] Add support for `units_metadata`
- Lark parser: rewrite and optimize, replacing all AI-generated code (from the Proof of Concept) for human-generated code.
- Add tests for temperature conversion
- Kelvins have no `delta_` counterpart on `Pint` (due to offset=0), is this correct?
- A conda-forge recipe

## Regarding the addition of new units

### Objective

To implement differences between UDUNITS2 and the CF standard

### References

I haven't found yet a single document from the CF team summarizing these diferences.

Current references:

-   [@trexfeathers](https://github.com/trexfeathers)
-   [CF Conventions : section "Units"](https://cf-convention.github.io/Data/cf-conventions/cf-conventions-1.13/cf-conventions.html#units)
-   [cf-units.Units](https://ncas-cms.github.io/cfunits/cfunits.Units.html)
-   [FAQs graybealski/cf-conventions-work](https://github.com/graybealski/cf-conventions-work/blob/master/FAQ.md#are-there-units-in-cf-that-arent-in-udunits), but updated 12 years ago, maybe outdated

### Context

List of new units not supported in UDUNITS2 (from `cfunits`):

| Unit name               | Symbol | Definition  | Status         |
|-------------------------|--------|-------------|----------------|
| level                   |        | 1           | New unit       |
| sigma_level             |        | 1           | New unit       |
| layer                   |        | 1           | New unit       |
| practical_salinity_unit | psu    | 1e-3        | New unit       |
| decibel                 | dB     | 1           | New unit       |
| bel                     |        | 10 dB       | New unit       |
| sverdrup                | Sv     | 1e6 m3 s-1  | Added symbol   |
| sievert                 |        | J kg-1      | Removed symbol |

including plural forms.

### Discussion points

#### Units `level`, `sigma-level`, `layer`

According to CF conventions docs, these are kept for backwards compatibility
with COARDS, but they are actually deprecated:

> As an exception, to maintain backwards compatibility with COARDS, the text
> strings level, layer, and sigma_level are allowed in the units attribute, in
> order to indicate dimensionless vertical coordinates. This use of units is not
> compatible with UDUNITS, and is deprecated by this standard because
> conventions for more precisely identifying dimensionless vertical coordinates
> are available

Proposal:

- To add them as adimensional units
- To show a Deprecation warning when used.

#### Units `sverdrup` and `sievert`

`udunits2-common.xml` has already added both. However, UDUNITS associates the
`Sv` symbol to `sievert` according to the SI unit-system. This diverges from `cf-units`'s implementation, that intentionally associates it to `sverdrup`.

Proposal:

- To confirm that `cf-units` has changed the assignment of `Sv` symbol according
  to the CF standard.
- To assign the symbol to `sverdrup` in consequence

#### Units `practical_salinity_unit`

According to FAQs:

> The unit PSU or practical salinity unit was used for salinity terms in CF, but
> is no longer used; rather, this is considered a dimensionless quantity (unit
> of 1).

According to `cf-units`, it should be defined as `1e-3` (correct), not `1`

Proposal:

- To add to the registry with definition `1e-3`
- Do we need to show a deprecation warning?

#### Units `decibel` (`bel`)

According to FAQs:

> decibel: a logarithmic measure of relative acoustic or energy intensity;
> symbol dB, db, or dbel (the reference level, needed for logarithmic units, is
> specified in the standard names that use this canonical unit)

`cf-units` defines `dB` as `1`, but this quote says that the reference level
for the logarithm should be read from the `standard_name` attribute.

Proposal:

- To add this unit as `1`.
- alternatively, explore if the `standard_name` could be taken into account at
  Units creation time (see the next section, shares procedure).

## Regarding the support of the `units_metadata` attribute

**Objective**: To support correct temperature and temperature-difference
conversions according to the `units_metadata` attribute (introduced in CF-1.11).

References:

-   [@aulemahal](https://github.com/aulemahal)
-   [CF Conventions : section "Temperature units"](https://cf-convention.github.io/Data/cf-conventions/cf-conventions-1.13/cf-conventions.html#temperature-units)
-   [Pint's docs : section "Temperature conversion"](https://pint.readthedocs.io/en/stable/user/nonmult.html)

### Context

From the CF docs:

> In order to convert the units correctly, it is essential to know whether a
> temperature is on-scale or a difference. Therefore this standard strongly
> recommends that any variable whose units involve a temperature unit should
> also have a `units_metadata` attribute to make the distinction. This attribute
> must have one of the following three values:
>
> - `temperature: on_scale`
> - `temperature: difference`
> - `temperature: unknown`.
>
> The `units_metadata` attribute, `standard_name` modifier and `cell_methods`
> attribute must be consistent if present. A variable must not have a
> `units_metadata` attribute if it has no `units` attribute or if its `units`
> do not involve a temperature unit.

Relevant notes for the implementation:

- if the `units_metadata` attribute is not present, the data-reader should assume `temperature: unknown`
- in CF versions < 1.11, should assume `temperature: unknown` unless it can be deduced from other metadata
- (for guidance) UDUNITS software assumes `temperature: on_scale` for units strings containing only a unit of temperature, and `temperature: difference` for units strings in which a unit of temperature is raised to any power other than unity, or multiplied or divided by any other unit.

Regarding the conversion:

> With `temperature: on_scale`, correct conversion can be guaranteed only for
> pure temperature units. If the quantity is an on-scale temperature multiplied
> by some other quantity, it is not possible to convert the data from the units
> given to any other units that involve a temperature with a different origin,
> given only the units.
> For instance, when temperature is on-scale, a value in `kg degree_C m-2` can
> be converted to a value in `kg K m-2` only if we know separately the values in
> `degree_C` and `kg m-2` of which it is the product.

Notes:

- **TODO**: I have to study the exact behaviour of the temperature conversion with `Pint`
- I have checked that Pint does not creates the `delta_` versions of Kelvins
  where the offset is 0 -> It needs to be investigated more, probably it is OK

### Implementation discussion

Before studying deeply the behaviour of `Pint` in temperature conversions, I
think the problem could be a matter of mapping the value of `units_metadata`
with prefixing the unit with `delta_`. This prefix is auto-generated by pint when
the unit definition has an offset different from `0`.


The `units_metadata` attribute could be mapped into Pint's units:

| units_metadata            | Pint Unit           | Multiplicative |
|---------------------------|---------------------|----------------|
| `temperature: on_scale`   | `<temp-unit>`       | No             |
| `temperature: difference` | `delta_<temp-unit>` | Yes            |
| `temperature: unknown`    |                     |                |

In order to map correctly the value of `temperature: unknown` with the unit definition,
I need to compare previously the consistency between the CF standard and `Pint` in converting ambiguous
temperature units.

Assuming we can map correctly this attribute to pint, that mapping can be
applyied by the UnitRegistry preprocessor added by `pint-cf`.
The problem is how we can pass `units_metadata` to the preprocessor since `Pint`
doesn't allows to pass custom metadata into the UnitRegistry.

I see 2 alternatives:

1. To subclass `pint.UnitRegistry`.
2. To use a [ContextVar](https://docs.python.org/3.14/library/contextvars.html)

#### Subclassing `pint.UnitRegistry`

The first option has the advantage of being fully customizable and easy to use.
Usage, more or less:

```python
ureg = cf_unitregistry()  # <pint_cf.UnitRegistry>

q = ureg("degree_C", units_metadata="temperature: difference")  # 1 delta_degree_Celsius
```

Being fully customizable could be useful in the long term depending on the library user's future needs. But I see
some drawbacks:

- the user stops to use the "native" `pint` classes in favour of `pint-cf`'s subclasses.
  It's assumed that user is already familiar with pint, so changing the "native"
  behaviour could lead to surprises in the users usage.
- Pint's API is limited and forces to use pint's private attributes.
  So we would adapt more for supporting the internal changes `pint` does between
  versions.

#### Using a ContextVar

The second option uses a `ContextVar` to pass the `units_metadata` to the
preprocessor. It could be done for instance by creating a Context Manager:

```python
ureg = cf_unitregistry()  # <pint.registry.UnitRegistry>

with UnitMetadata("temperature: difference"):
    q = ureg("degree_C") # 1 delta_degree_Celsius
```

it passes the `units_metadata` to the processor effectively and preventing the
drawbacks of subclassing the `UnitRegistry`.

I think it is a better option unless having the need of a
UnitRegistry subclass for the future.
