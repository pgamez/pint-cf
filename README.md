# pint-cf

**THIS PROJECT IS UNDER DEVELOPMENT**

CF-compliant UnitRegistry and formatter for Pint.

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
