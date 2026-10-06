import pytest

from app.parsers.mapping import (
    SCALAR_FIELDS,
    FieldMapping,
    apply_mapping,
    suggest_mapping,
)


def test_field_mapping__rejects_other_ids_target_without_key() -> None:
    with pytest.raises(ValueError):
        FieldMapping(targets={"EID": "other_ids."})


def test_field_mapping__rejects_exclusive_target_mapped_from_two_inputs() -> None:
    with pytest.raises(ValueError, match="several inputs"):
        FieldMapping(targets={"Year": "year", "Publication Year": "year"})


def test_field_mapping__rejects_page_target_mapped_from_two_inputs() -> None:
    with pytest.raises(ValueError, match="several inputs"):
        FieldMapping(targets={"A": "page_start", "B": "page_start"})


def test_field_mapping__allows_list_target_from_several_inputs() -> None:
    mapping = FieldMapping(targets={"A": "authors", "B": "authors"})

    assert mapping.targets == {"A": "authors", "B": "authors"}


def test_field_mapping__rejects_unknown_target_field() -> None:
    with pytest.raises(ValueError):
        FieldMapping(targets={"Title": "not_a_real_field"})


def test_scalar_fields__are_the_records_optional_string_fields() -> None:
    assert SCALAR_FIELDS == {
        "title",
        "abstract",
        "journal",
        "conference_name",
        "volume",
        "issue",
        "pages",
        "doi",
        "pmid",
        "issn",
        "isbn",
        "publication_type",
        "language",
        "publisher",
        "url",
        "notes",
    }


def test_apply_mapping__first_non_empty_value_wins_for_scalar() -> None:
    mapping = FieldMapping(targets={"A": "title", "B": "title", "C": "title"})

    record = apply_mapping({"A": "", "B": "First", "C": "Second"}, mapping)

    assert record.title == "First"


@pytest.mark.parametrize(
    ("raw_fields", "expected"),
    [
        ({"SP": "10", "EP": "20"}, "10-20"),
        ({"SP": "10", "EP": ""}, "10"),
        ({"SP": "", "EP": "20"}, "20"),
        ({"SP": "", "EP": ""}, None),
    ],
)
def test_apply_mapping__joins_page_start_and_end(
    raw_fields: dict[str, str], expected: str | None
) -> None:
    mapping = FieldMapping(targets={"SP": "page_start", "EP": "page_end"})

    assert apply_mapping(raw_fields, mapping).pages == expected


def test_apply_mapping__explicit_pages_win_over_start_and_end() -> None:
    mapping = FieldMapping(
        targets={"Pages": "pages", "SP": "page_start", "EP": "page_end"}
    )

    record = apply_mapping({"Pages": "5-9", "SP": "10", "EP": "20"}, mapping)

    assert record.pages == "5-9"


def test_suggest_mapping__strict_matches_exact_aliases_only() -> None:
    aliases = {"title": ["ti"], "doi": ["do"]}

    suggestions = suggest_mapping(["TI", "tj", "Custom ID"], aliases, lenient=False)

    assert suggestions.targets == {"TI": "title"}


def test_suggest_mapping__exclusive_target_prefers_alias_rank_over_file_order() -> None:
    aliases = {"date": ["da", "py", "y1"]}

    suggestions = suggest_mapping(["PY", "Y1", "DA"], aliases, lenient=False)

    assert suggestions.targets == {"DA": "date"}


def test_suggest_mapping__exclusive_target_tie_keeps_first_in_file() -> None:
    aliases = {"year": ["year"]}

    suggestions = suggest_mapping(["Year", "YEAR"], aliases, lenient=False)

    assert suggestions.targets == {"Year": "year"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020///", (2020, None, None)),
        ("2020/05//", (2020, 5, None)),
        ("2020/05/14/", (2020, 5, 14)),
        ("2020/05/14/Spring", (2020, 5, 14)),
        ("2020///Spring", (2020, None, None)),
    ],
)
def test_apply_mapping__parses_ris_style_date(
    value: str, expected: tuple[int, int | None, int | None]
) -> None:
    mapping = FieldMapping(targets={"DA": "date"})

    date = apply_mapping({"DA": value}, mapping).publication_date

    assert date is not None
    assert (date.year, date.month, date.day) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020 May 14", (2020, 5, 14)),
        ("2020 May", (2020, 5, None)),
        ("2020 Jan-Feb", (2020, 1, None)),
        ("2020 Oct 3", (2020, 10, 3)),
    ],
)
def test_apply_mapping__parses_nbib_style_date(
    value: str, expected: tuple[int, int | None, int | None]
) -> None:
    mapping = FieldMapping(targets={"DP": "date"})

    date = apply_mapping({"DP": value}, mapping).publication_date

    assert date is not None
    assert (date.year, date.month, date.day) == expected


def test_suggest_mapping__lenient_fuzzy_matches_and_falls_back_to_id() -> None:
    aliases = {"title": ["article title"]}

    suggestions = suggest_mapping(
        ["Article Titles", "Custom ID"], aliases, lenient=True
    )

    assert suggestions.targets == {
        "Article Titles": "title",
        "Custom ID": "other_ids.custom_id",
    }
