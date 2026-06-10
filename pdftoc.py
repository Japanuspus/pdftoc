#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pypdf",
# ]
# ///

"""Add table of contents entries to PDF document

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
Offset: 4
  1   1 Introduction
 10   2 Background
 13     2.1 Previous Work
 15     2.2 Our Approach
 18   3 Conclusion
 ```
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import NamedTuple

import pypdf


class TocEntry(NamedTuple):
    pdf_page_number: int
    header_level: int
    title: str


def parse_toc_file(toc_file: Path) -> list[TocEntry]:
    """Parse the table of contents file and return a list of entries.

    Each entry is a tuple of (pdf_page_number, header_level, title).
    Header level is determined by the spacing between page number and title.
    """
    entries: list[TocEntry] = []
    offset = 0
    min_spacing = None  # Minimum spacing, used as reference for header levels
    
    line_pattern = re.compile(r"^(\s*)(-?\d+)(\s+)(.*)$")

    with toc_file.open("r", encoding="utf-8") as f:
        line = next(f)  # Read the first line for offset
        if not line.startswith("Offset:"):
            raise ValueError("First line of TOC file must start with 'Offset:'")
        offset = int(line.split(":")[1].strip())

        for line in (l for l in (l.strip() for l in f) if l):  # Skip empty lines
            m=line_pattern.match(line)
            if not m:
                raise ValueError(f"Malformed line in TOC file: {line}")
            
            page_number = int(m.group(2))

            # Count spaces between page number and title
            spacing = len(m.group(3))
            # Set minimum spacing from first entry
            if min_spacing is None:
                min_spacing = spacing
            header_level = (spacing - min_spacing) // 2
            if not (spacing - min_spacing) % 2 == 0:
                raise ValueError(f"Invalid spacing for header level in line: {line}")

            title = m.group(4)
            pdf_page_number = page_number + offset
            entries.append(TocEntry(pdf_page_number, header_level, title))
    
    entries.sort()  # Ensure entries are sorted by page number
    return entries


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

def main(argv: list[str] | None = None) -> int:

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
    try:
        toc_entries = parse_toc_file(toc_file)
        add_pdf_toc(pdf_path, toc_entries, output_file)
        print(f"Successfully created PDF with TOC: {output_file}")
        return 0
    except Exception as e:
        print(f"Error processing PDF: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
