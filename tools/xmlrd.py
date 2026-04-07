"""
https://pint.readthedocs.io/en/stable/advanced/defining.html

Falta:

- Comprobar unidades
- Añadir descripciones como comentarios
- Derived units? [density] = [mass] / [volume]

"""

import textwrap
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as ET

from pint_cf.parser import cf_string_to_pint

NO_SYMBOL = "_"
_NAME_SIZE = 128

_DIMENSIONS = {
    "meter": "[length]",
    "kilogram": "[mass]",
    "second": "[time]",
    "ampere": "[current]",
    "kelvin": "[temperature]; offset: 0",
    "mole": "[substance]",
    "candela": "[luminosity]",
}


class BaseElement(ABC):
    comment: str | None = None

    @abstractmethod
    def spec(self) -> list[str]: ...

    def __str__(self) -> str:
        return " = ".join(self.spec())


class Prefix(BaseElement):
    def __init__(self, value: str, name: str, symbols: Iterable[str]) -> None:
        self.value = value
        self.name = name
        self.symbols = symbols

    def spec(self) -> list[str]:
        return [f"{self.name}-", self.value, *(f"{s}-" for s in self.symbols)]


class Name(BaseElement):
    def __init__(
        self,
        singular: str,
        plural: str | None,
        noplural: bool = False,
        comment: str | None = None,
    ) -> None:
        self._singular = singular
        self._plural = plural
        self.noplural = noplural
        self.comment = comment

    @property
    def singular(self) -> str:
        return self._singular

    @property
    def plural(self) -> str | None:
        if self.noplural:
            return

        if self._plural:
            return self._plural

        singular = self.singular

        if not singular:
            return None

        length = len(singular)

        if length + 3 >= _NAME_SIZE:
            return None

        if length == 0:
            return None

        if length == 1:
            return f"{singular}s"

        last_char = singular[-1]

        if last_char == "y":
            penultimate = singular[-2]
            if penultimate in "aeiou":
                return f"{singular}s"
            else:
                return f"{singular[:-1]}ies"
        elif last_char in "sxz" or (length >= 2 and singular[-2:] in ["ch", "sh"]):
            return f"{singular}es"
        else:
            return f"{singular}s"

    def spec(self) -> list[str]:
        if self.plural:
            return [self.singular, self.plural]
        else:
            return [self.singular]


class Symbol(BaseElement):
    def __init__(self, symbol, comment: str | None = None) -> None:
        self.symbol = symbol
        self.comment = comment

    def spec(self) -> list[str]:
        return [self.symbol]


class BaseUnit(BaseElement):
    description: str | None = None

    @property
    @abstractmethod
    def name(self) -> Name | None: ...

    @property
    @abstractmethod
    def symbol(self) -> Symbol | None: ...

    @property
    @abstractmethod
    def aliases(self) -> Iterable[Name | Symbol]: ...

    @property
    def spec_comments(self) -> dict[str, str]:
        params = {}

        if self.name and self.name.comment:
            params[str(self.name)] = self.name.comment

        if self.symbol and self.symbol.comment:
            params[str(self.symbol)] = self.symbol.comment

        for alias in self.aliases or []:
            if alias.comment:
                params[str(alias)] = alias.comment

        return params


class Unit(BaseUnit):
    def __init__(
        self,
        name: Name,
        symbol: Symbol | None = None,
        definition: str | None = None,
        description: str | None = None,
        aliases: Iterable[Name | Symbol] | None = None,
        is_base: bool = False,
        is_dimensionless: bool = False,
        comment: str | None = None,
    ) -> None:
        self._name = name
        self._symbol = symbol or Symbol(NO_SYMBOL)
        self._aliases = aliases or []
        self.definition = definition
        self.is_base = is_base
        self.is_dimensionless = is_dimensionless
        self.description = description
        self.comment = comment

    @property
    def name(self) -> Name:
        return self._name

    @property
    def symbol(self) -> Symbol:
        return self._symbol

    @property
    def aliases(self) -> Iterable[Name | Symbol]:
        return self._aliases

    def spec(self) -> list[str]:
        line = [self.name.singular, self.definition, *self.symbol.spec()]

        if self.name.plural:
            line.append(self.name.plural)

        for i in self.aliases:
            line.extend(i.spec())

        return line


class Alias(BaseUnit):
    def __init__(
        self,
        target: str,
        aliases: Iterable[Name | Symbol] | None = None,
        description: str | None = None,
        comment: str | None = None,
    ) -> None:
        self.target = target
        self._aliases = aliases or []
        self.description = description
        self.comment = comment

    @property
    def name(self) -> None:
        pass

    @property
    def symbol(self) -> None:
        pass

    @property
    def aliases(self) -> Iterable[Name | Symbol]:
        return self._aliases

    def spec(self) -> list[str]:
        line = [f"@alias {self.target}"]
        for i in self.aliases:
            line.extend(i.spec())

        return line


class Constant(BaseUnit):
    def __init__(
        self,
        symbol: Symbol,
        definition: str,
        aliases: Iterable[Name | Symbol] | None = None,
        description: str | None = None,
        comment: str | None = None,
    ) -> None:
        self._symbol = symbol
        self.definition = definition
        self._aliases = aliases or []
        self.description = description
        self.comment = comment

    @property
    def name(self) -> None:
        pass

    @property
    def symbol(self) -> Symbol:
        return self._symbol

    @property
    def aliases(self) -> Iterable[Name | Symbol]:
        return self._aliases

    def spec(self) -> list[str]:
        line = [str(self.symbol), self.definition]
        for i in self.aliases:
            line.extend(i.spec())

        return line


class _UnitReference:
    def __init__(
        self,
    ) -> None:
        self.reference = {}

    def add(self, unit: Unit) -> None:
        if unit.name is None:
            raise ValueError("Unit must have a name to be added to reference")

        name = unit.name.singular

        self.reference |= {
            unit.name.singular: name,
            unit.symbol.symbol: name,
            unit.definition: name,
        }

        for i in unit.aliases:
            for j in i.spec():
                self.reference[j] = name

    def __getitem__(self, key):
        return self.reference[key]

    def __contains__(self, item):
        return item in self.reference

    def get(self, key: str) -> str | None:
        return self.reference.get(key)


UnitReference = _UnitReference()


def parse_prefix(element: Element) -> Prefix:
    value = element.findtext("value")
    name = element.findtext("name")
    symbols = [i.text or "" for i in element.findall("symbol")]

    if value is None:
        raise ValueError("Prefix element missing value")
    if name is None:
        raise ValueError("Prefix element missing name")

    return Prefix(value, name, symbols)


def _parse_name(element: Element) -> Name:
    singular = element.findtext("singular")
    plural = element.findtext("plural")
    noplural = element.find("noplural") is not None
    comment = element.attrib.get("comment")

    if singular is None:
        raise ValueError("Unit name missing singular element")

    return Name(
        singular=singular,
        plural=plural,
        noplural=noplural,
        comment=comment,
    )


def _parse_symbol(element: Element) -> Symbol:
    symbol = element.text
    comment = element.attrib.get("comment")

    if symbol is None:
        raise ValueError("Symbol element missing text")

    return Symbol(symbol=symbol, comment=comment)


class _UnitElement:
    def __init__(self, element: Element) -> None:
        name = element.find("name")
        symbol = element.find("symbol")
        definition = element.findtext("def")
        description = element.findtext("definition")
        comment = element.findtext("comment")
        is_base = element.find("base") is not None
        is_dimensionless = element.find("dimensionless") is not None

        if name is not None:
            name = _parse_name(name)

        if symbol is not None:
            symbol = _parse_symbol(symbol)

        if is_base and name is not None:
            definition = _DIMENSIONS[name.singular]
        elif is_dimensionless:
            definition = "[]"
        elif definition:
            definition = cf_string_to_pint(definition)
        else:
            raise ValueError("Unit element missing name and def")

        aliases = []
        _force_noplural = False

        for i in element.find("aliases") or []:
            match i.tag:
                case "noplural":
                    # BUG: In XML file there are <noplural/> elements
                    # inside <aliases>, which causes process_entry to
                    # raise an error.
                    # We should attach to the Name element instead of
                    # treating it as an alias.
                    #
                    # Cases:
                    #   - (udunits2-common.xml:117) in "avogadro_constant"
                    #   - (udunits2-common.xml:126) in "percent"
                    _force_noplural = True
                case "name":
                    aliases.append(_parse_name(i))
                case "symbol":
                    aliases.append(_parse_symbol(i))
                case _:
                    raise ValueError(f"Unexpected alias element: {i.tag}")

        if _force_noplural:
            for i in aliases:
                if isinstance(i, Name):
                    i.noplural = True

        # Attributes
        self.name = name
        self.symbol = symbol
        self.definition = definition
        self.description = description
        self.comment = comment
        self.is_base = is_base
        self.is_dimensionless = is_dimensionless
        self.aliases = aliases


def parse_unit(element: Element) -> BaseUnit:
    u = _UnitElement(element)

    if u.name is not None:
        unit = Unit(
            name=u.name,
            symbol=u.symbol,
            definition=u.definition,
            description=u.description,
            aliases=u.aliases,
            is_base=u.is_base,
            is_dimensionless=u.is_dimensionless,
            comment=u.comment,
        )

        UnitReference.add(unit)
        return unit

    elif u.definition is None:
        raise ValueError("Unit element missing name and def")

    elif reference := UnitReference.get(u.definition):
        # If the definition has already been processed, we
        # should have a name for it, so we create an alias
        return Alias(
            target=reference,
            aliases=u.aliases,
            description=u.description,
            comment=u.comment,
        )

    # Otherwise we have to process the aliases to find a
    # name for the unit from the aliases, and then we can
    # create a normal unit definition

    name = None
    symbol = None
    aliases = []

    for i in u.aliases:
        if name is None and isinstance(i, Name):
            name = i
        elif symbol is None and isinstance(i, Symbol):
            symbol = i
        else:
            aliases.append(i)

    if name is not None:
        return Unit(
            name=name,
            symbol=symbol,
            definition=u.definition,
            aliases=aliases,
            description=u.description,
            comment=u.comment,
        )

    elif symbol is not None:
        # If there is no name in the aliases, we create an
        # instance of UnitConstant
        return Constant(
            symbol=symbol,
            definition=u.definition,
            aliases=aliases,
            description=u.description,
            comment=u.comment,
        )

    raise ValueError("Unit element missing name and symbol")


def gen_pint_registry(f: TextIO, write_doc: bool = True) -> None:
    print("Processing", f.name, "...")

    filepath = Path(f.name)
    filedir = filepath.parent

    tree = ET.parse(f)
    root = tree.getroot()

    if root is None:
        raise ValueError("Failed to parse udunits2.xml")

    if root.tag != "unit-system":
        raise ValueError(f"Unexpected root element: {root.tag}")

    with filepath.with_suffix(".txt").open("w") as out:
        print("> writing to", out.name, "...")
        print("# Generated from", filepath.name, file=out, end="\n\n")

        for child in root:
            match child.tag:
                case "import":
                    if not child.text:
                        raise ValueError("Import element missing text")

                    imported_xml = filedir.joinpath(child.text)
                    imported_txt = imported_xml.with_suffix(".txt").relative_to(filedir)

                    print("@import", imported_txt, file=out)

                    with imported_xml.open() as fi:
                        gen_pint_registry(fi, write_doc)

                case "prefix":
                    prefix = parse_prefix(child)
                    print(prefix, file=out)

                case "unit":
                    unit = parse_unit(child)
                    if write_doc:
                        print(file=out)

                        doc = []
                        if unit.description:
                            doc.append(
                                textwrap.fill(
                                    f"# {unit.description}",
                                    subsequent_indent="# ",
                                )
                            )
                        if unit.comment:
                            doc.append(
                                textwrap.fill(
                                    f"# [comment] {unit.comment}",
                                    subsequent_indent="# ",
                                )
                            )

                        for param, comment in unit.spec_comments.items():
                            doc.append(
                                textwrap.fill(
                                    f"# [comment @ {param}] {comment}",
                                    subsequent_indent="# ",
                                )
                            )

                        doc = "\n".join(doc)

                        if doc:
                            print(doc, file=out)

                    print(unit, file=out)

    # def __str__(self) -> str:
    #     line = [self.name.singular, self.definition, str(self.symbol)]

    #     if self.name.plural:
    #         line.append(self.name.plural)

    #     line += [str(alias) for alias in self.aliases]
    #     entry = " = ".join(line)

    #     if self.description:
    #         comment = textwrap.fill(self.description, subsequent_indent="# ")
    #         return f"\n# {comment}\n{entry}"

    #     return entry
