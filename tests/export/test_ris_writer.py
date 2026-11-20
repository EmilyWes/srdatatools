import pytest

from app.cleaning.steps import PUBLICATION_TYPES
from app.export.ris import CURATED_TAGS, RIS_TAGS, TAG_PATTERN, TYPE_CODES, ris_type


def test_ris_tags__curated_tags_come_first() -> None:
    assert list(RIS_TAGS)[: len(CURATED_TAGS)] == list(CURATED_TAGS)


def test_ris_tags__all_are_valid_tags() -> None:
    assert all(TAG_PATTERN.fullmatch(tag) for tag in RIS_TAGS)


def test_ris_tags__end_tag_not_offered() -> None:
    assert "ER" not in RIS_TAGS


def test_type_codes__cover_every_standard_type() -> None:
    assert set(TYPE_CODES) == set(PUBLICATION_TYPES)


@pytest.mark.parametrize(
    ("stored", "code"),
    [
        ("Journal article", "JOUR"),
        ("Review", "JOUR"),
        ("Book chapter", "CHAP"),
        ("Conference paper", "CONF"),
        ("Conference abstract", "ABST"),
        ("Preprint", "UNPB"),
        ("Erratum", "JOUR"),
    ],
)
def test_ris_type__standard_type(stored: str, code: str) -> None:
    assert ris_type(stored) == code


@pytest.mark.parametrize("stored", ["CPAPER", "EDBOOK", "JOUR"])
def test_ris_type__ris_code_passes_through(stored: str) -> None:
    assert ris_type(stored) == stored


@pytest.mark.parametrize(
    ("stored", "code"),
    [("Article", "JOUR"), ("inproceedings", "CONF"), ("phdthesis", "THES")],
)
def test_ris_type__uncleaned_value_via_cleaning_aliases(stored: str, code: str) -> None:
    assert ris_type(stored) == code


def test_ris_type__first_line_of_several() -> None:
    assert ris_type("Article\nReview") == "JOUR"


@pytest.mark.parametrize("stored", [None, "", "Something else"])
def test_ris_type__unknown_or_empty_is_generic(stored: str | None) -> None:
    assert ris_type(stored) == "GEN"
