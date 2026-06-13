import pdftoc
import io
import pytest


SAMPLE_TOC_TEXT_1 = r"""
1 Introduction . 6
2 Background . 10
    2.1 Previous Work . 13
    2.2 Our Approach . 15
3 Conclusion . 18
""".lstrip("\n")


SAMPLE_TOC_TEXT_2 = r"""
---
offset=5
indent_size=2
parser_regex="^\\s*(?P<page_number>\\d+)(?P<indent>\\s+)(?P<title>.*)$"
---
  1   1 Introduction
  5   2 Background
  8     2.1 Previous Work
 10     2.2 Our Approach
 13   3 Conclusion
""".lstrip("\n")


def test_toc_text():
    toc_text = io.StringIO(SAMPLE_TOC_TEXT_2)
    assert next(toc_text).strip() == "---"


@pytest.mark.parametrize("sample", [SAMPLE_TOC_TEXT_1, SAMPLE_TOC_TEXT_2])
def test_parse_toc_file(sample):
    toc_text = io.StringIO(sample)
    expected_entries = [
        pdftoc.TocEntry(pdf_page_number=6, header_level=0, title="1 Introduction"),
        pdftoc.TocEntry(pdf_page_number=10, header_level=0, title="2 Background"),
        pdftoc.TocEntry(pdf_page_number=13, header_level=1, title="2.1 Previous Work"),
        pdftoc.TocEntry(pdf_page_number=15, header_level=1, title="2.2 Our Approach"),
        pdftoc.TocEntry(pdf_page_number=18, header_level=0, title="3 Conclusion"),
    ]
    entries = pdftoc.parse_toc_file(toc_text)
    assert entries == expected_entries, f"Expected {expected_entries}, got {entries}"
