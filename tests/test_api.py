import pint

from pint_cf import cf_set_application_registry, cf_unitregistry


def test_cf_unitregistry_registers_cf_formatter() -> None:
    ureg = cf_unitregistry()
    q = ureg("1 m/s^2")

    assert f"{q:cf}" == "1.0 meter-second^-2"
    assert f"{q:~cf}" == "1.0 m/s2"


def test_cf_set_application_registry_sets_global_registry() -> None:
    cf_set_application_registry()
    ureg = pint.get_application_registry()
    q = ureg("1 m/s^2")

    assert f"{q:cf}" == "1.0 meter-second^-2"
    assert f"{q:~cf}" == "1.0 m/s2"
