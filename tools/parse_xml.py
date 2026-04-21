import logging
import shutil
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write the output files (default: same as input file)",
    )
    args = parser.parse_args()

    output_files: list[Path] = []
    with args.filename.open() as f:
        for output_file in gen_pint_registry(f):
            output_files.append(output_file)

    if args.output_dir:
        for output_file in output_files:
            dest = args.output_dir / output_file.name
            print("Moving", output_file, "->", dest, "...")
            shutil.move(output_file, dest)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
