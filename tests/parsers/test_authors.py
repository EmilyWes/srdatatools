import pytest

from app.parsers.authors import (
    add_author_id,
    clean_author_id,
    ids_by_key,
    merge_author_ids,
)


def test_clean_author_id__strips_spaces_and_orcid_url() -> None:
    assert clean_author_id(" https://orcid.org/0000-0002-1825-0097") == (
        "0000-0002-1825-0097"
    )


def test_add_author_id__identical_id_collapses() -> None:
    assert add_author_id("2", "2") == "2"


def test_add_author_id__different_ids_are_joined() -> None:
    assert add_author_id("1", "9") == "1 | 9"
    assert add_author_id("1 | 9", "9") == "1 | 9"


def test_add_author_id__to_or_of_nothing() -> None:
    assert add_author_id("", "1") == "1"
    assert add_author_id("1", "") == "1"


def test_ids_by_key__one_value_per_author_per_key() -> None:
    slots = [
        [("orcid", "1"), ("scopus_author_id", "2")],
        [],
        [("scopus_author_id", "3")],
    ]

    assert ids_by_key(slots) == {
        "orcid": ["1", "", ""],
        "scopus_author_id": ["2", "", "3"],
    }


def test_ids_by_key__same_key_twice_for_one_author() -> None:
    slots = [[("scopus_author_id", "1"), ("scopus_author_id", "9")]]

    assert ids_by_key(slots) == {"scopus_author_id": ["1 | 9"]}


def test_ids_by_key__strips_orcid_url() -> None:
    slots = [[("orcid", "https://orcid.org/0000-0002-1825-0097")]]

    assert ids_by_key(slots) == {"orcid": ["0000-0002-1825-0097"]}


def test_ids_by_key__no_ids_is_empty() -> None:
    assert ids_by_key([[], []]) == {}
    assert ids_by_key([]) == {}


def test_merge_author_ids__adds_ids_per_author() -> None:
    merged = merge_author_ids({"b": ["1", ""]}, "b", ["1", "2"])

    assert merged == {"b": ["1", "2"]}


def test_merge_author_ids__new_key_is_added() -> None:
    assert merge_author_ids({"a": ["1"]}, "b", ["2"]) == {"a": ["1"], "b": ["2"]}


def test_merge_author_ids__different_author_count_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    merged = merge_author_ids({"b": ["1", "2"]}, "b", ["3"])

    assert merged == {"b": ["1", "2"]}
    assert "'b'" in caplog.text
