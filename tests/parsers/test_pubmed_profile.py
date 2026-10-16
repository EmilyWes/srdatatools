import pytest

from app.models.record import Record
from app.parsers.nbib import parse_nbib_text, suggest_nbib_mapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.pubmed import PUBMED, expand_page_range


def _parse_nbib(text: str) -> Record:
    tags = list(dict.fromkeys(line[:4].strip() for line in text.splitlines()))
    profile = PUBMED.formats["nbib"]
    mapping = suggest_nbib_mapping(tags, profile.aliases)
    result = apply_profile(parse_nbib_text(text, mapping), profile)
    return result.rows[0].record


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ("521-2", "521-522"),
        ("3705-6", "3705-3706"),
        ("1199-201", "1199-1201"),
        ("1-2", "1-2"),
        ("589-594", "589-594"),
        ("121354", "121354"),
        ("e123", "e123"),
        ("S12-5", "S12-5"),
    ],
)
def test_expand_page_range__expands_only_abbreviated_numeric_ranges(
    pages: str, expected: str
) -> None:
    assert expand_page_range(pages) == expected


def test_pubmed_nbib__journal_uses_jt_not_ta() -> None:
    record = _parse_nbib("PMID- 1\nTA  - Nature\nJT  - Nature reviews\n")

    assert record.journal == "Nature reviews"


def test_pubmed_nbib__not_available_title_uses_tt() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - [Not Available].\nTT  - Clin d'oeil du Dinosaure.\n"
    )

    assert record.title == "Clin d'oeil du Dinosaure."


def test_pubmed_nbib__not_available_title_without_tt_is_none() -> None:
    record = _parse_nbib("PMID- 1\nTI  - [Not Available].\n")

    assert record.title is None


def test_pubmed_nbib__bracketed_translated_title_is_kept() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - [Introduction to paleopathology].\nTT  - Introduction.\n"
    )

    assert record.title == "[Introduction to paleopathology]."


def test_pubmed_nbib__expands_abbreviated_pages() -> None:
    record = _parse_nbib("PMID- 1\nPG  - 521-2\n")

    assert record.pages == "521-522"


def test_pubmed_nbib__keeps_first_publication_type() -> None:
    record = _parse_nbib(
        "PMID- 1\nPT  - Journal Article\nPT  - Retracted Publication\n"
    )

    assert record.publication_type == "Journal Article"


def test_pubmed_nbib__keeps_first_isbn() -> None:
    record = _parse_nbib("PMID- 1\nISBN- 978-3-319-28801-7\nISBN- 978-3-319-28802-4\n")

    assert record.isbn == "978-3-319-28801-7"


def test_pubmed_nbib__leaves_ordinary_record_unchanged() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - Some Paper.\nPG  - 589-594\nPT  - Letter\n"
        "ISBN- 978-3-319-28801-7\n"
    )

    assert record.title == "Some Paper."
    assert record.pages == "589-594"
    assert record.publication_type == "Letter"
    assert record.isbn == "978-3-319-28801-7"
