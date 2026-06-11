import pdftoc
import textwrap
import io
import pytest

@pytest.fixture
def toc_text():    
    toc_text = textwrap.dedent(r"""
        ---
        offset=21
        indent_size=4
        parser_regex="^(?P<indent>\\s*)(?P<title>.*)\\s*\\. (?P<page_number>\\d+)$"
        #parser_regex="^(?P<indented_title>.*)\\s*\\. (?P<page_number>\\d+)$"
        ---
        Introduction . 1
        I TRANSITION AMPLITUDES IN ELECTRODYNAMICS Introduction . 5
            A. Probability Amplitude Associated with a Physical Process . 7
            B. Time Dependence of Transition Amplitudes. 9
                1. Coupling between Discrete Isolated States . 9
        """[1:])
    return io.StringIO(toc_text)

def test_toc_text(toc_text):
    assert next(toc_text).strip() == "---"

def test_parse_toc_file(toc_text):
    expected_entries = [
        pdftoc.TocEntry(pdf_page_number=22, header_level=0, title="Introduction"),
        pdftoc.TocEntry(pdf_page_number=26, header_level=0, title="I TRANSITION AMPLITUDES IN ELECTRODYNAMICS Introduction"),
        pdftoc.TocEntry(pdf_page_number=28, header_level=1, title="A. Probability Amplitude Associated with a Physical Process"),
        pdftoc.TocEntry(pdf_page_number=30, header_level=1, title="B. Time Dependence of Transition Amplitudes"),
        pdftoc.TocEntry(pdf_page_number=30, header_level=2, title="1. Coupling between Discrete Isolated States"),
    ]

    entries = pdftoc.parse_toc_file(toc_text)
    assert entries == expected_entries, f"Expected {expected_entries}, got {entries}"

