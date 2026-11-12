import pytest

from app.parsers.authors import (
    author_from_name,
    author_id,
    format_author_ids,
    merge_author_ids,
    parse_author_ids,
)


def test_author_from_name__splits_family_and_given_on_separator() -> None:
    author = author_from_name("Smith, John A.", ",")

    assert author.full_name == "Smith, John A."
    assert author.family_name == "Smith"
    assert author.given_name == "John A."


def test_author_from_name__ambiguous_name_is_not_split_by_default() -> None:
    author = author_from_name("Smith, Jr., John", ", ")

    assert author.full_name == "Smith, Jr., John"
    assert author.family_name is None
    assert author.given_name is None


def test_author_from_name__ambiguous_name_splits_at_first_separator() -> None:
    author = author_from_name("Smith, Jr., John", ", ", "first")

    assert author.family_name == "Smith"
    assert author.given_name == "Jr., John"


def test_author_from_name__ambiguous_name_splits_at_last_separator() -> None:
    author = author_from_name("Smith, Jr., John", ", ", "last")

    assert author.family_name == "Smith, Jr."
    assert author.given_name == "John"


def test_author_from_name__without_separator_keeps_full_name_only() -> None:
    author = author_from_name("Müller RT", ", ")

    assert author.full_name == "Müller RT"
    assert author.family_name is None
    assert author.given_name is None


def test_author_from_name__splits_given_first_name() -> None:
    author = author_from_name("John Smith", " ", family_first=False)

    assert author.family_name == "Smith"
    assert author.given_name == "John"


def test_author_from_name__given_first_ambiguous_name_splits_at_last_separator() -> (
    None
):
    author = author_from_name("John Paul Smith", " ", "last", family_first=False)

    assert author.family_name == "Smith"
    assert author.given_name == "John Paul"


def test_author_id__prefixes_key_and_strips_orcid_url() -> None:
    assert author_id("orcid", " https://orcid.org/0000-0002-1825-0097") == (
        "orcid:0000-0002-1825-0097"
    )


def test_format_author_ids__joins_ids_and_authors() -> None:
    slots = [["orcid:1", "scopus_author_id:2"], [], ["scopus_author_id:3"]]

    assert format_author_ids(slots) == "orcid:1, scopus_author_id:2||scopus_author_id:3"


def test_format_author_ids__drops_duplicates_within_an_author() -> None:
    assert format_author_ids([["scopus_author_id:2", "scopus_author_id:2"]]) == (
        "scopus_author_id:2"
    )


def test_format_author_ids__all_empty_is_none() -> None:
    assert format_author_ids([[], []]) is None
    assert format_author_ids([]) is None


def test_parse_author_ids__inverts_format() -> None:
    slots = [["orcid:1", "scopus_author_id:2"], [], ["scopus_author_id:3"]]

    assert parse_author_ids(format_author_ids(slots)) == slots


def test_parse_author_ids__empty_value_has_no_authors() -> None:
    assert parse_author_ids(None) == []
    assert parse_author_ids("") == []


def test_merge_author_ids__adds_ids_per_author() -> None:
    merged = merge_author_ids([["a:1"], []], [["b:1"], ["b:2"]], "author ids")

    assert merged == [["a:1", "b:1"], ["b:2"]]


def test_merge_author_ids__first_ids_set_the_authors() -> None:
    assert merge_author_ids([], [["b:1"], []], "author ids") == [["b:1"], []]


def test_merge_author_ids__different_author_count_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    merged = merge_author_ids([["a:1"], ["a:2"]], [["b:1"]], "author ids")

    assert merged == [["a:1"], ["a:2"]]
    assert "author ids" in caplog.text
