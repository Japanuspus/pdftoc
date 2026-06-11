#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pypdf",
# ]
# ///

r"""Add table of contents entries to PDF document

The table of contents file should be a text file with one entry per line, formatted as follows:
```
Offset: <number to add to listed page number to get pdf page number>
<optional spaces>page_number<spacing>title
```
There may be any number of spaces before the page number.
The spaces after the number are used to signify indentation level. 
Spacing count x0 between the first page number and title sets the minimum indent, max header level.
All subsequent entries must have spacing x which is an even number above x0, i.e. x=x0+2*k. This line is assigned header level k.

Example:
```
---
offset=4
---
  1   1 Introduction
 10   2 Background
 13     2.1 Previous Work
 15     2.2 Our Approach
 18   3 Conclusion
 ```


 Example:
```
---
offset=5
indent_size=4
parser_regex="^(?P<indented_title>.*)\s+\. (?P<page_number>\d+)$"
---
1 Introduction . 1
2 Background . 10   
    2.1 Previous Work . 13   
    2.2 Our Approach . 15   
3 Conclusion . 18   
 ```

"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path
import re
import sys
import tomllib
from typing import NamedTuple, TextIO
import typing

import pypdf


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
    indent_size=2,
    parser_regex=r"^(\s*)(?P<page_number>-?\d+)(?P<indent>\s+)(?P<title>.+)$"
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
    header_text = '\n'.join(itertools.takewhile(lambda line: not line.startswith("---"), lines))
    data = tomllib.loads(header_text) 
    return TocConfig(
        *(data.get(k, default) for k, default in DEFAULT_TOC_CONFIG._asdict().items())
    )


def parse_toc_entries(lines: typing.Iterator[str], config: TocConfig) -> list[TocEntry]:
    entries: list[TocEntry] = []
    min_spacing = None  # Baseline for spacing-derived levels
    line_pattern = re.compile(config.parser_regex)

    for line in (l.rstrip() for l in lines):
        if not line:  # Skip empty lines
            continue

        m = line_pattern.match(line)
        if not m:
            raise ValueError(f"Malformed line in TOC file: \"{line}\" does not match parser_regex: r'{config.parser_regex}'")

        groups = m.groupdict()
        try:
            page_number = int(groups["page_number"])
            title = groups["title"].strip()
            indent = groups["indent"]
        except KeyError:
            raise ValueError(f"Missing group 'page_number', 'indent', or 'title' in parser_regex: {config.parser_regex} for line: {line}")
        
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


def parse_toc_file(lines: typing.TextIO) -> list[TocEntry]:
    """Parse the table of contents file and return a list of entries.

    Each entry is a tuple of (pdf_page_number, header_level, title).
    Header level is determined by spacing between page number and title when
    the regex defines a `spacing` group, otherwise by leading indentation.
    """
    [lines] = itertools.tee(lines, 1) #make lines forkable for lookahead
    config = parse_toc_header(lines)
    print(f"Parsed TOC config: {config}")
    return parse_toc_entries(lines, config)


def add_pdf_toc(
    pdf_file: Path, toc_entries: list[TocEntry], output_file: Path
) -> None:
    """Add table of contents to PDF document as bookmarks.
    
    Args:
        pdf_file: Path to the input PDF file.
        toc_entries: List of (pdf_page_number, header_level, title) tuples.
        output_file: Path to save the output PDF with TOC.
    """
    
    print(f"Adding TOC to PDF: {pdf_file}")
    writer = pypdf.PdfWriter(clone_from=str(pdf_file))
    writer.page_mode = "/UseOutlines"
    
    
    # Track outline items at each level to set correct parent relationships
    outline_stack = {}
    
    print(f"Processing {len(toc_entries)} TOC entries:")
    for pdf_page_number, header_level, title in toc_entries:
        # Adjust for 0-based indexing in pypdf
        page_idx = pdf_page_number - 1
        
        # Clamp page index to valid range
        page_idx = max(0, min(page_idx, len(writer.pages) - 1))
        
        # Get parent outline item for this level
        parent = outline_stack.get(header_level - 1, None)
        if parent:
            outline_item = writer.add_outline_item(title, page_idx, parent=parent)
            print(f"  Added TOC entry page index {page_idx:4d}, level {header_level:02d} with parent:    '{title}'")
        else:
            outline_item = writer.add_outline_item(title, page_idx)
            print(f"  Added TOC entry page index {page_idx:4d}, level {header_level:02d} without parent: '{title}'")
        
        # Store this item as potential parent for deeper levels
        outline_stack[header_level] = outline_item
        
        # Remove items at deeper levels since we're now at a shallower level
        for level in list(outline_stack.keys()):
            if level > header_level:
                del outline_stack[level]
    
    # Write output PDF with TOC
    writer.write(output_file)
    print(f"TOC added successfully. Output saved to: {output_file}")


def main(argv: list[str]):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument("-t", "--toc-file", dest="toc_file", default=None,
                        help="Path for file with toc as detailed above. Defaults to <name>-toc.txt")
    parser.add_argument("-o", "--output", dest="output_file", default=None,
                        help="Path to save the output PDF file. Defaults to <name>-toc.pdf")
    parser.add_argument("pdf_file", help="Path to the PDF file to convert.")

    args = parser.parse_args(argv)
    
    # Derive base name from pdf_file for defaults
    pdf_path = Path(args.pdf_file)
    base_name = pdf_path.stem  # Filename without extension
    pdf_dir = pdf_path.parent
    
    # Set default values for optional arguments if not provided
    toc_file = Path(args.toc_file) if args.toc_file else pdf_dir / f"{base_name}-toc.txt"
    output_file = Path(args.output_file) if args.output_file else pdf_dir / f"{base_name}-toc.pdf"
    
    # Validate input PDF exists
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {args.pdf_file}", file=sys.stderr)
        return 1
    
    # Validate TOC file exists
    if not toc_file.exists():
        print(f"Error: TOC file not found: {toc_file}", file=sys.stderr)
        return 1
    
    # Parse TOC file and add to PDF
    with toc_file.open(encoding="utf-8") as f:
        toc_entries = parse_toc_file(f)
    add_pdf_toc(pdf_path, toc_entries, output_file)
    print(f"Successfully created PDF with TOC: {output_file}")


if __name__ == "__main__":
    main(sys.argv[1:])
