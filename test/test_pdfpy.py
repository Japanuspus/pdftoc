import pdftoc
import io
import pytest
import pypdf


@pytest.fixture
def sample_pdf():
    """Create a sample in-memory PDF with 20 pages."""
    writer = pypdf.PdfWriter()
    for _ in range(20):
        writer.add_blank_page(width=612, height=792)

    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes


def test_add_pdf_toc_basic(sample_pdf):
    """Test adding TOC entries to a PDF."""
    toc_entries = [
        pdftoc.TocEntry(pdf_page_number=1, header_level=0, title="Chapter 1"),
        pdftoc.TocEntry(pdf_page_number=5, header_level=1, title="Section 1.1"),
        pdftoc.TocEntry(pdf_page_number=10, header_level=0, title="Chapter 2"),
    ]

    output_pdf = io.BytesIO()
    pdftoc.add_pdf_toc(sample_pdf, toc_entries, output_pdf, remove_existing=False)

    # Verify the output PDF has outline entries
    output_pdf.seek(0)
    reader = pypdf.PdfReader(output_pdf)
    assert len(reader.outline) > 0
    assert reader.outline[0].title == "Chapter 1"


def test_add_pdf_toc_with_remove_existing(sample_pdf):
    """Test that remove_existing flag clears pre-existing outline entries."""
    # First, add some TOC entries
    initial_entries = [
        pdftoc.TocEntry(pdf_page_number=1, header_level=0, title="Old Chapter"),
    ]
    temp_pdf = io.BytesIO()
    pdftoc.add_pdf_toc(sample_pdf, initial_entries, temp_pdf, remove_existing=False)
    temp_pdf.seek(0)

    # Verify initial outline exists
    reader = pypdf.PdfReader(temp_pdf)
    assert len(reader.outline) > 0
    assert reader.outline[0].title == "Old Chapter"

    # Now add new entries with remove_existing=True
    temp_pdf.seek(0)
    new_entries = [
        pdftoc.TocEntry(pdf_page_number=2, header_level=0, title="New Chapter"),
    ]
    output_pdf = io.BytesIO()
    pdftoc.add_pdf_toc(temp_pdf, new_entries, output_pdf, remove_existing=True)

    # Verify only new entries are present
    output_pdf.seek(0)
    final_reader = pypdf.PdfReader(output_pdf)
    assert len(final_reader.outline) > 0
    assert final_reader.outline[0].title == "New Chapter"


def test_read_toc_basic(sample_pdf):
    """Test reading TOC entries from a PDF with outline."""
    # Add some TOC entries first
    toc_entries = [
        pdftoc.TocEntry(pdf_page_number=1, header_level=0, title="Introduction"),
        pdftoc.TocEntry(pdf_page_number=5, header_level=1, title="Background"),
    ]
    pdf_with_toc = io.BytesIO()
    pdftoc.add_pdf_toc(sample_pdf, toc_entries, pdf_with_toc, remove_existing=False)

    # Read back the TOC
    pdf_with_toc.seek(0)
    reader = pypdf.PdfReader(pdf_with_toc)
    output = io.StringIO()
    pdftoc._read_toc(reader, reader.outline, output)

    # Verify output format
    output_text = output.getvalue()
    assert "Introduction" in output_text
    assert "Background" in output_text
    assert ". 1" in output_text  # page number


def test_read_toc_nested_hierarchy(sample_pdf):
    """Test reading TOC with nested hierarchy."""
    toc_entries = [
        pdftoc.TocEntry(pdf_page_number=1, header_level=0, title="Chapter 1"),
        pdftoc.TocEntry(pdf_page_number=3, header_level=1, title="Section 1.1"),
        pdftoc.TocEntry(pdf_page_number=4, header_level=2, title="Subsection 1.1.1"),
    ]
    pdf_with_toc = io.BytesIO()
    pdftoc.add_pdf_toc(sample_pdf, toc_entries, pdf_with_toc, remove_existing=False)

    # Read back the TOC
    pdf_with_toc.seek(0)
    reader = pypdf.PdfReader(pdf_with_toc)
    output = io.StringIO()
    pdftoc._read_toc(reader, reader.outline, output)

    # Verify indentation levels in output
    output_lines = output.getvalue().strip().split("\n")
    assert len(output_lines) >= 3
    # First item should have no indent
    assert not output_lines[0].startswith("  ")
    # Second item should have 2 spaces (level 1)
    assert output_lines[1].startswith("  ")
    # Third item should have 4 spaces (level 2)
    assert output_lines[2].startswith("    ")
