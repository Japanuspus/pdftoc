#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pypdf",
# ]
# ///

r"""pdftoc: Manipulate outline/table of contents (TOC) entries in PDF document

To write an outline/TOC to a PDF document `myfile.pdf`, create a text file `myfile-toc.txt` with the desired entries:

```
1 Introduction . 6
2 Background . 10
    2.1 Previous Work . 13
    2.2 Our Approach . 15
3 Conclusion . 18
```
Then run `pdftoc` as follows to create a new PDF `myfile-toc.pdf` with the outline entries:

```bash
> pdftoc write myfile.pdf
```

To read out an existing outline, run `pdftoc read myfile-toc.pdf`.

Run `pdftoc write --help` or `pdftoc read --help` for more options.

TOC file format
---------------
By default, the lines of the TOC file (`myfile-toc.txt` above) are expected to have format:

    {indent with four spaces per level}{Entry title}{any number of spaces or dots}{page number}

Indent is computed relative to first line, so the first line can have any amount of leading spaces.
As detailed below, the page number can be adjusted by adding an offset (default 0) to get the PDF page number.
To work with files in differet formats, the parser can be configured by adding a TOML header to the TOC file.
The header is delimited by lines containing `---` and can specify the following fields:

- `offset`: Number to add to the listed page number to get the PDF page number. Default is 0.
- `indent_size`: Number of spaces that correspond to one level of indentation. Default is 4.
- `parser_regex`: Regular expression with named groups `indent`, `title`, and `page_number` to parse each line.


 Example (this parses to same toc entries as the default format example above):
```
---
offset=5
indent_size=2
parser_regex="^\\s*(?P<page_number>\\d+)(?P<indent>\\s+)(?P<title>.*)$"
---
  1   1 Introduction
  4   2 Background
  8     2.1 Previous Work
 10     2.2 Our Approach
 13   3 Conclusion
```

"""

from __future__ import annotations

import argparse
import itertools
import logging
from pathlib import Path
import re
import sys
import tomllib
from typing import NamedTuple
import typing

import pypdf
from pypdf.generic import Destination

logger = logging.getLogger(__name__)


class CliError(Exception):
    """Raised for expected CLI failures that should exit with code 1."""


class TocEntry(NamedTuple):
    pdf_page_number: int
    header_level: int
    title: str


class TocConfig(NamedTuple):
    offset: int
    indent_size: int
    parser_regex: str


DEFAULT_TOC_CONFIG = TocConfig(
    offset=0,
    indent_size=4,
    parser_regex=r"^(?P<indent>\s*)(?P<title>.+?)[\.\s]+(?P<page_number>-?\d+)$",
)


# https://docs.python.org/3/library/itertools.html#itertools.tee example of lookahead with tee to peek at the next line without consuming it
def lookahead(tee_iterator):
    "Return the next value without moving the input forward"
    [forked_iterator] = itertools.tee(tee_iterator, 1)
    return next(forked_iterator)


def parse_toc_header(lines: typing.Iterator[str]) -> TocConfig:
    """Parse TOML header and return config"""

    if not lookahead(lines).startswith("---"):
        return DEFAULT_TOC_CONFIG
    _ = next(lines)  # Consume the '---' line
    header_text = "\n".join(
        itertools.takewhile(lambda line: not line.startswith("---"), lines)
    )
    data = tomllib.loads(header_text)
    return TocConfig(
        *(data.get(k, default) for k, default in DEFAULT_TOC_CONFIG._asdict().items())
    )


def parse_toc_entries(lines: typing.Iterator[str], config: TocConfig) -> list[TocEntry]:
    entries: list[TocEntry] = []
    min_spacing = None  # Baseline for spacing-derived levels
    line_pattern = re.compile(config.parser_regex)

    for line in (line_raw.rstrip() for line_raw in lines):
        if not line:  # Skip empty lines
            continue

        m = line_pattern.match(line)
        if not m:
            raise ValueError(
                f"Malformed line in TOC file: \"{line}\" does not match parser_regex: r'{config.parser_regex}'"
            )

        groups = m.groupdict()
        try:
            page_number = int(groups["page_number"])
            title = groups["title"].strip()
            indent = groups["indent"]
        except KeyError:
            raise ValueError(
                f"Missing group 'page_number', 'indent', or 'title' in parser_regex: {config.parser_regex} for line: {line}"
            )

        # Convert indent to header level based on minimum spacing
        spacing = len(indent)
        if min_spacing is None:
            min_spacing = spacing
        indent_spacing = spacing - min_spacing
        if indent_spacing < 0 or indent_spacing % config.indent_size != 0:
            raise ValueError(f"Invalid spacing for header level in line: {line}")
        header_level = indent_spacing // config.indent_size

        pdf_page_number = page_number + config.offset
        entry = TocEntry(pdf_page_number, header_level, title)
        entries.append(entry)

    entries.sort()  # Ensure entries are sorted by page number
    return entries


def parse_toc_file(lines: typing.Iterable[str]) -> list[TocEntry]:
    """Parse the table of contents file and return a list of entries.

    Each entry is a tuple of (pdf_page_number, header_level, title).
    Header level is determined by spacing between page number and title when
    the regex defines a `spacing` group, otherwise by leading indentation.
    """
    [lines] = itertools.tee(lines, 1)  # make lines forkable for lookahead
    config = parse_toc_header(lines)
    logger.debug(f"Parsed TOC config: {config}")
    return parse_toc_entries(lines, config)


def add_pdf_toc(
    pdf_file: typing.BinaryIO,
    toc_entries: list[TocEntry],
    output_file: typing.BinaryIO,
    remove_existing: bool = False,
) -> None:
    """Add table of contents to PDF document as bookmarks.

    Args:
        pdf_file: Path to the input PDF file.
        toc_entries: List of (pdf_page_number, header_level, title) tuples.
        output_file: Path to save the output PDF with TOC.
    """

    logger.info(f"Adding TOC to PDF: {pdf_file}")
    writer = pypdf.PdfWriter(clone_from=pdf_file)
    writer.page_mode = "/UseOutlines"

    if remove_existing:
        writer.get_outline_root().empty_tree()

    # Track outline items at each level to set correct parent relationships
    outline_stack = {}

    logger.debug(f"Processing {len(toc_entries)} TOC entries:")
    for pdf_page_number, header_level, title in toc_entries:
        # Adjust for 0-based indexing in pypdf
        page_idx = pdf_page_number - 1

        # Clamp page index to valid range
        page_idx = max(0, min(page_idx, len(writer.pages) - 1))

        # Get parent outline item for this level
        parent = outline_stack.get(header_level - 1, None)
        if parent:
            outline_item = writer.add_outline_item(title, page_idx, parent=parent)
            logger.debug(
                f"Added TOC entry page index {page_idx:4d}, level {header_level:02d} with parent: '{title}'"
            )
        else:
            outline_item = writer.add_outline_item(title, page_idx)
            logger.debug(
                f"Added TOC entry page index {page_idx:4d}, level {header_level:02d} without parent: '{title}'"
            )

        # Store this item as potential parent for deeper levels
        outline_stack[header_level] = outline_item

        # Remove items at deeper levels since we're now at a shallower level
        for level in list(outline_stack.keys()):
            if level > header_level:
                del outline_stack[level]

    # Write output PDF with TOC
    writer.write(output_file)


def _read_toc(
    pdf_reader: pypdf.PdfReader,
    outlines: list[Destination | list],
    out: typing.TextIO,
    level: int = 0,
) -> None:
    """Recursively print all outline items with indentation."""

    for item in outlines:
        if isinstance(item, list):
            _read_toc(pdf_reader, item, out, level + 1)
            continue

        page_number = pdf_reader.get_destination_page_number(item)
        indent = "  " * level

        if page_number is None:
            print(f"{indent} {item.title}", file=out)
        else:
            print(f"{indent} {item.title} . {page_number + 1}", file=out)


def read_toc(pdf_reader: pypdf.PdfReader, out: typing.TextIO) -> None:
    _read_toc(pdf_reader, pdf_reader.outline, out)


def add_write_subparser(subparsers: argparse._SubParsersAction) -> None:
    def handle_write(args: argparse.Namespace) -> None:
        pdf_path = Path(args.pdf_file)

        if not pdf_path.exists():
            raise CliError(f"PDF file not found: {args.pdf_file}")

        output_file_path = (
            pdf_path.with_stem(pdf_path.stem + "-toc")
            if args.output_file is None
            else Path(args.output_file)
        )

        toc_entries = parse_toc_file(args.toc_file) if args.toc_file else []
        with output_file_path.open("wb") as output_file, pdf_path.open("rb") as pdf_file:
            add_pdf_toc(
                pdf_file,
                toc_entries,
                output_file,
                remove_existing=not args.retain_existing,
            )
        logger.info(f"Successfully created PDF with TOC: {output_file_path}")

    write_parser = subparsers.add_parser(
        "write",
        help="Write a table of contents from a text file into a PDF",
    )
    write_parser.add_argument(
        "-t",
        "--toc-file",
        dest="toc_file",
        type=argparse.FileType("r", encoding="utf-8"),
        default=None,
        help="Path for file with toc. Use - for stdin.",
    )
    write_parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        default=None,
        help="Path to save the output PDF file. Defaults to <name>-toc.pdf",
    )
    write_parser.add_argument(
        "--retain-existing",
        action="store_true",
        default=False,
        help="Retain existing outline items in the PDF instead of removing them.",
    )
    write_parser.add_argument("pdf_file", help="Path to the PDF file to update.")
    write_parser.set_defaults(handler=lambda args: handle_write(args))


def add_read_subparser(subparsers: argparse._SubParsersAction) -> None:
    def handle_read(args: argparse.Namespace) -> None:
        pdf_reader = pypdf.PdfReader(args.pdf_file)
        read_toc(pdf_reader, args.output_file)

    read_parser = subparsers.add_parser(
        "read",
        help="Read and print an existing PDF outline",
    )
    read_parser.add_argument(
        "pdf_file",
        type=argparse.FileType("rb"),
        help="Path to the PDF file to inspect.",
    )
    read_parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        type=argparse.FileType("w", encoding="utf-8"),
        default="-",
        help="Path to save the output toc file. Use - for stdout. Defaults to stdout.",
    )
    read_parser.set_defaults(handler=lambda args: handle_read(args))




def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity level (can be repeated: -vv for extra verbose)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    add_write_subparser(subparsers)
    add_read_subparser(subparsers)

    args = parser.parse_args(argv)

    # Configure logging based on verbosity
    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

    try:
        args.handler(args)
    except CliError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main(sys.argv[1:])
