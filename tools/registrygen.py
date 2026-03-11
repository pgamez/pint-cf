#!/usr/bin/env python3
"""
https://pint.readthedocs.io/en/stable/advanced/defining.html
"""

import logging
from argparse import ArgumentParser
from pathlib import Path

import defusedxml.ElementTree as ET

from pint_cf.parser import cf_string_to_pint

_logger = logging.getLogger(__name__)

NAME_SIZE = 128


def add_prefix(f, prefix):
    data = {
        "name": None,
        "value": None,
        "symbol": [],
        "aliases": [],
    }

    for i in prefix:
        match i.tag:
            case "name":
                data["name"] = f"{i.text}-"
            case "value":
                data["value"] = i.text
            case "symbol":
                data["symbol"].append(f"{i.text}-")

    print(
        data["name"],
        data["value"],
        *data["symbol"],
        sep=" = ",
        file=f,
    )


_DIMENSIONS = {
    "meter": "[length]",
    "kilogram": "[mass]",
    "second": "[time]",
    "ampere": "[current]",
    "kelvin": "[temperature]; offset: 0",
    "mole": "[substance]",
    "candela": "[luminosity]",
}


_MAPPED_PROCESSED = {}


class Name:
    def __init__(self, element):
        self.element = element

    @property
    def singular(self) -> str:
        return self.element.find("singular").text

    @property
    def plural(self) -> str | None:
        if self.element.find("noplural") is not None:
            return

        plural = self.element.find("plural")
        if plural is not None:
            return plural.text

        singular = self.singular

        if not singular:
            return None

        length = len(singular)

        if length + 3 >= NAME_SIZE:
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


class Unit:
    def __init__(self, element):
        self.element = element

        self.base = True if element.find("base") is not None else False
        self.dimensionless = (
            True if element.find("dimensionless") is not None else False
        )

    @property
    def name(self) -> Name | None:
        if (elem := self.element.find("name")) is not None:
            return Name(elem)

    @property
    def symbol(self) -> str | None:
        elem = self.element.find("symbol")
        if elem is not None:
            return elem.text

        elif self.aliases:
            return "_"

    @property
    def aliases(self) -> list[str]:
        data = []
        aliases = self.element.find("aliases")

        if aliases is not None:
            for alias in aliases.findall("name"):
                name = Name(alias)
                data.append(name.singular)
                if name.plural:
                    data.append(name.plural)

            for alias in aliases.findall("symbol"):
                data.append(alias.text)

        return data

    @property
    def definition(self):
        elem = self.element.find("definition")
        if elem is not None:
            return elem.text

    @property
    def def_(self):
        if self.base:
            if self.name is None:
                raise ValueError("Base unit must have a name")
            else:
                return _DIMENSIONS[self.name.singular]

        elif self.dimensionless:
            return "[]"
        else:
            return cf_string_to_pint(self.element.find("def").text)

    def write(self, f):
        if self.name:
            # Save the name for later use in case this unit is used as
            # an alias for another unit
            _MAPPED_PROCESSED[self.name.singular] = self.name.singular
            _MAPPED_PROCESSED[self.def_] = self.name.singular
            _MAPPED_PROCESSED[self.symbol] = self.name.singular
            for i in self.aliases:
                _MAPPED_PROCESSED[i] = self.name.singular

            plurals = []
            if self.name.plural:
                plurals.append(self.name.plural)

            print(
                self.name.singular,
                self.def_,
                self.symbol,
                *self.aliases,
                *plurals,
                sep=" = ",
                file=f,
            )

        else:
            name = _MAPPED_PROCESSED.get(self.def_)
            if name:
                # If the definition has already been processed, we
                # should have a name for it, so we can just create an
                # alias
                print(f"@alias {name}", *self.aliases, sep=" = ", file=f)
            else:
                # If the definition has not been processed, then it is
                # a constant
                print(self.aliases[0], self.def_, *self.aliases[1:], sep=" = ", file=f)


def parse_udunits2(f, tree, datadir: Path):
    root = tree.getroot()

    if root is None:
        raise ValueError("Failed to parse udunits2.xml")

    if root.tag != "unit-system":
        raise ValueError(f"Unexpected root element: {root.tag}")

    for child in root:
        match child.tag:
            case "import":
                _logger.debug(f"Importing units from {child.text}")

                # filename = RESOURCE_DIR.joinpath(child.text)
                filename = datadir.joinpath(child.text)
                if not filename.is_file():
                    raise FileNotFoundError(f"Included file {filename} not found")

                txtfile = Path(child.text).with_suffix(".txt")
                print("@import", txtfile, file=f)
                included_tree = ET.parse(filename.open())

                output_dir = Path(f.name).parent.resolve()
                with Path(output_dir, txtfile).open("w") as fp:
                    parse_udunits2(fp, included_tree, datadir)

            case "prefix":
                add_prefix(f, child)

            case "unit":
                unit = Unit(child)
                unit.write(f)
            case _:
                break


def load_unit_system():
    parser = ArgumentParser(
        description="Parse udunits2.xml and generate a pint definition file"
    )
    parser.add_argument(
        "filename", type=Path, help="Path to the output pint definition file"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("udunits2.txt"),
        help="Path to the output pint definition file (default: udunits2.txt)",
    )
    args = parser.parse_args()

    datadir = args.filename.parent.resolve()
    tree = ET.parse(args.filename.open())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        parse_udunits2(f, tree, datadir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    load_unit_system()
