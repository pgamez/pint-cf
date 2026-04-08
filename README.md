# pint-cf

This is a Pint extension that implements the CF-compliant UnitRegistry and formatter.

## Features

This package provides:

- A CF-compliant Pint UnitRegistry, with explicit plurals.
- A custom formatter `cf`, supporting both long and short (symbol) formats.

Known limitations:

- Pint does not support neither **time coordinates** (e.g.
  `days since 2001-01-01`) nor **climate calendars** (e.g.: `360_days`).
  Consider using [cftime](https://unidata.github.io/cftime/) for that.
- Pint does not support **scaling factors** in Unit expressions (e.g.
  `pint.Unit('0.1 m')`). You can solve it by adding your own unit definition.

## Usage

```python
from pint_cf import cf_unitregistry

ureg = cf_unitregistry()

q = ureg('10 meters per second^2').to('km s-2')

print(f"{q:cf}")   # 0.01 kilometer-second^-2
print(f"{q:~cf}")  # 0.01 km/s2
```

If you prefer Pint's global application registry:

```python
import pint
from pint_cf import cf_set_application_registry

cf_set_application_registry()
ureg = pint.get_application_registry()
```
