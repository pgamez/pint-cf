from pint_cf import cf_unitregistry


def test_cf_unitregistry_registers_cf_formatter() -> None:
    ureg = cf_unitregistry()
    q = ureg("1 m/s^2")

    assert f"{q:cf}" == "1.0 meter-second^-2"
    assert f"{q:~cf}" == "1.0 m/s2"
