import pytest

from app.parsers.authors import (
    author_id,
    author_id_keys,
    author_ids_for_key,
    format_author_ids,
    merge_author_ids,
    parse_author_ids,
)


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


_UNSPLIT = "orcid:[0000-1; 0000-2], scopus_author_id:[1, 2]"
_CLEANED = "orcid:1, scopus_author_id:2||scopus_author_id:3"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_UNSPLIT, ["orcid", "scopus_author_id"]),
        (_CLEANED, ["orcid", "scopus_author_id"]),
        (None, []),
    ],
)
def test_author_id_keys__first_seen_order(
    value: str | None, expected: list[str]
) -> None:
    assert author_id_keys(value) == expected


def test_author_ids_for_key__unsplit_value_as_stored() -> None:
    assert author_ids_for_key(_UNSPLIT, "orcid", " / ") == "0000-1; 0000-2"
    assert author_ids_for_key(_UNSPLIT, "pmid", " / ") == ""


def test_author_ids_for_key__cleaned_one_slot_per_author() -> None:
    assert author_ids_for_key(_CLEANED, "orcid", "; ") == "1; ; "
    assert author_ids_for_key(_CLEANED, "scopus_author_id", "; ") == "2; ; 3"
    assert author_ids_for_key(_CLEANED, "pmid", "; ") == "; ; "


def test_author_ids_for_key__same_key_twice_for_one_author() -> None:
    value = "scopus_author_id:1, scopus_author_id:9|scopus_author_id:2"

    assert author_ids_for_key(value, "scopus_author_id", "; ") == "1, 9; 2"


def test_author_ids_for_key__no_ids_is_empty() -> None:
    assert author_ids_for_key(None, "orcid", "; ") == ""
