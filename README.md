# pint-cf

This package extends Pint with a CF-compliant unit registry and formatter.

## Features

This package provides:

- A CF-compliant Pint UnitRegistry with explicit plural aliases.
- A custom `cf` formatter that supports both long-name and short-symbol formats.

Known limitations:

- Pint does not support **time coordinates** (e.g.
  `days since 2001-01-01`) or **climate calendars** (e.g., `360_days`).
  Consider using [cftime](https://unidata.github.io/cftime/) instead.
- Pint does not support **scaling factors** in unit expressions, such as
  `1.5 * pint.Unit('0.1 m')`. You can work around this by adding your own
  [unit definition](https://pint.readthedocs.io/en/stable/advanced/defining.html#programmatically).

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
