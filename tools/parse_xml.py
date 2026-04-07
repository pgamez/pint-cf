import logging
from argparse import ArgumentParser
from pathlib import Path

from xmlrd import gen_pint_registry


def main():
    parser = ArgumentParser(
        description="Parse udunits2.xml and generate a pint definition file"
    )
    parser.add_argument(
        "filename", type=Path, help="Path to the output pint definition file"
    )
    args = parser.parse_args()

    with args.filename.open() as f:
        gen_pint_registry(f)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
