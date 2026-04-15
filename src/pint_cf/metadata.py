from contextvars import ContextVar, Token
from types import TracebackType
from typing import Self

import pint
from pint.facets.plain import PlainUnit

UNITS_METADATA: ContextVar[str | None] = ContextVar("units_metadata", default=None)


class UnitsMetadata:
    def __init__(self, metadata_str: str | None = None) -> None:
        self._metadata_str = metadata_str
        self._token: Token[str | None] | None = None

    def __enter__(self) -> None:
        self._token = UNITS_METADATA.set(self._metadata_str)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._token is not None:
            UNITS_METADATA.reset(self._token)

    @classmethod
    def from_unit(cls, unit: PlainUnit) -> Self:
        dimensionality = unit._REGISTRY.get_dimensionality(unit)
        if dimensionality == "[temperature]":
            if unit._REGISTRY._is_multiplicative(str(unit)):
                return cls("temperature: difference")
            else:
                return cls("temperature: on_scale")
        return cls(None)

    @classmethod
    def from_quantity(cls, quantity: pint.Quantity) -> Self:
        return cls.from_unit(quantity.units)

    def to_str(self) -> str:
        return self._metadata_str or ""
