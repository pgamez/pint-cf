# pint-cf

**THIS PROJECT IS UNDER DEVELOPMENT**

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
import pint
from pint_cf.units import setup_cf_registry


setup_cf_registry()
ureg = pint.get_application_registry()
print(ureg.get())  # <pint.registry.UnitRegistry object at 0x7f1337144080>

q = ureg('10 meters per second^2').to('km s-2')

print(f"{q:cf}")   # 0.01 kilometer-second^-2
print(f"{q:~cf}")  # 0.01 km/s2
```
