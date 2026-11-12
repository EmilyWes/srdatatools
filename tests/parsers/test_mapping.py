import logging

import pytest
from pydantic import ValidationError

from app.models.record import Label
from app.parsers.mapping import (
    AuthorsRow,
    DateRow,
    FieldMapping,
    IssnIsbnRow,
    KeywordsRow,
    LabelRow,
    OtherIdRow,
    PagesRow,
    ScalarRow,
    Suggest,
    apply_mapping,
    default_row,
    make_row,
    normalize_label,
    override_aliases,
    parse_date_string,
    parse_unsplit_keywords,
    split_keyword,
    suggest_mapping,
    tag_keyword,
    unsplit_keywords,
)
from app.parsers.quirks import ParseSettings
from tests.mappings import mapping_of


def test_field_mapping__rejects_other_id_without_key() -> None:
    with pytest.raises(ValidationError):
        FieldMapping.model_validate({"rows": {"EID": {"target": "other_ids"}}})


def test_field_mapping__rejects_unknown_target_field() -> None:
    with pytest.raises(ValidationError):
        FieldMapping.model_validate({"rows": {"Title": {"target": "not_a_field"}}})


def test_field_mapping__round_trips_through_a_dump() -> None:
    mapping = mapping_of(
        {"DA": Suggest("date", {"part": "year"}), "AU": "authors", "L": "label"}
    )

    assert FieldMapping.model_validate(mapping.model_dump()) == mapping


def test_default_row__fills_each_targets_default_options() -> None:
    assert default_row("title", "TI") == ScalarRow(target="title")
    assert default_row("date", "DA") == DateRow(part="full")
    assert default_row("pages", "PG") == PagesRow(part="range")
    assert default_row("issn_isbn", "SN") == IssnIsbnRow(kind="auto")
    assert default_row("other_ids", "Work ID") == OtherIdRow(key="work_id")
    assert default_row("authors", "Author IDs") == AuthorsRow(
        role="names", id_key="author_ids"
    )
    assert default_row("keywords", "KW") == KeywordsRow()
    assert default_row("label", "L") == LabelRow(phase="ft", screener="screener 1")


def test_default_row__rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="unknown Record field"):
        default_row("not_a_field", "X")


def test_make_row__applies_suggested_options_over_defaults() -> None:
    row = make_row(Suggest("authors", {"role": "ids"}), "ORCID")

    assert row == AuthorsRow(role="ids", id_key="orcid")


def test_make_row__rejects_invalid_option() -> None:
    with pytest.raises(ValidationError):
        make_row(Suggest("date", {"part": "week"}), "DA")


def test_apply_mapping__first_non_empty_value_wins_for_scalar() -> None:
    mapping = mapping_of({"A": "title", "B": "title", "C": "title"})

    record = apply_mapping({"A": "", "B": "First", "C": "Second"}, mapping)

    assert record.title == "First"


def test_apply_mapping__use_first_reads_chosen_keys_first_in_listed_order() -> None:
    mapping = mapping_of({"A": "title", "B": "title", "C": "title"})
    raw = {"A": "a", "B": "b", "C": "c"}

    assert apply_mapping(raw, mapping, ParseSettings(use_first=("C",))).title == "c"
    assert apply_mapping(raw, mapping, ParseSettings(use_first=("B", "C"))).title == (
        "b"
    )


def test_apply_mapping__use_first_falls_back_when_chosen_key_is_empty() -> None:
    mapping = mapping_of({"A": "title", "B": "title"})
    settings = ParseSettings(use_first=("B",))

    assert apply_mapping({"A": "a", "B": ""}, mapping, settings).title == "a"


def test_apply_mapping__use_first_ignores_keys_not_in_mapping() -> None:
    mapping = mapping_of({"A": "title", "B": "title"})
    settings = ParseSettings(use_first=("Z",))

    assert apply_mapping({"A": "a", "B": "b"}, mapping, settings).title == "a"


def test_apply_mapping__use_first_picks_the_names_column() -> None:
    mapping = mapping_of({"AU": "authors", "AF": "authors"})
    raw = {"AU": "Doe, J", "AF": "Doe, Jane"}

    record = apply_mapping(raw, mapping, ParseSettings(use_first=("AF",)))

    assert record.author_names == "Doe, Jane"


def test_apply_mapping__other_id_uses_row_key() -> None:
    mapping = mapping_of({"Work ID": Suggest("other_ids", {"key": "openalex"})})

    record = apply_mapping({"Work ID": "W1"}, mapping)

    assert record.other_ids == {"openalex": "W1"}


_START_END = {
    "SP": Suggest("pages", {"part": "start"}),
    "EP": Suggest("pages", {"part": "end"}),
}


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
    assert apply_mapping(raw_fields, mapping_of(_START_END)).pages == expected


def test_apply_mapping__page_range_wins_over_start_and_end() -> None:
    mapping = mapping_of({"Pages": "pages", **_START_END})

    record = apply_mapping({"Pages": "5-9", "SP": "10", "EP": "20"}, mapping)

    assert record.pages == "5-9"


def test_apply_mapping__page_count_gives_end_page() -> None:
    mapping = mapping_of(
        {
            "SP": Suggest("pages", {"part": "start"}),
            "N": Suggest("pages", {"part": "count"}),
        }
    )

    assert apply_mapping({"SP": "10", "N": "5"}, mapping).pages == "10-14"


def test_apply_mapping__end_page_wins_over_page_count() -> None:
    mapping = mapping_of({**_START_END, "N": Suggest("pages", {"part": "count"})})

    assert apply_mapping({"SP": "10", "EP": "12", "N": "5"}, mapping).pages == "10-12"


def test_apply_mapping__non_numeric_page_count_keeps_start_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mapping = mapping_of(
        {
            "SP": Suggest("pages", {"part": "start"}),
            "N": Suggest("pages", {"part": "count"}),
        }
    )

    with caplog.at_level(logging.WARNING):
        pages = apply_mapping({"SP": "e12", "N": "5"}, mapping).pages

    assert pages == "e12"
    assert "e12" in caplog.text


def test_apply_mapping__first_value_wins_per_page_part() -> None:
    mapping = mapping_of({"A": "pages", "B": "pages"})

    assert apply_mapping({"A": "", "B": "3-4"}, mapping).pages == "3-4"


_SN = mapping_of({"SN": "issn_isbn"})


@pytest.mark.parametrize("value", ["1234-5678", "12345678", "1234-567X"])
def test_apply_mapping__issn_isbn_routes_issn(value: str) -> None:
    record = apply_mapping({"SN": value}, _SN)

    assert (record.issn, record.isbn) == (value, None)


@pytest.mark.parametrize(
    "value",
    ["0-306-40615-2", "0306406152", "978-3-16-148410-0", "9783161484100"],
)
def test_apply_mapping__issn_isbn_routes_isbn(value: str) -> None:
    record = apply_mapping({"SN": value}, _SN)

    assert (record.issn, record.isbn) == (None, value)


def test_apply_mapping__issn_isbn_keeps_the_whole_value() -> None:
    value = "1234-5678 (electronic), 9123-4567 (print)"

    assert apply_mapping({"SN": value}, _SN).issn == value


def test_apply_mapping__issn_isbn_auto_goes_by_first_valid_number() -> None:
    value = "12345 (x), 979-840072171-7 (ISBN); 1234-5678"

    record = apply_mapping({"SN": value}, _SN)

    assert (record.issn, record.isbn) == (None, value)


def test_apply_mapping__issn_isbn_unrecognised_value_goes_to_issn_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        record = apply_mapping({"SN": "12345"}, _SN)

    assert (record.issn, record.isbn) == ("12345", None)
    assert "12345" in caplog.text


def test_apply_mapping__issn_isbn_empty_value_sets_nothing() -> None:
    record = apply_mapping({"SN": "  "}, _SN)

    assert (record.issn, record.isbn) == (None, None)


@pytest.mark.parametrize("kind", ["issn", "isbn"])
def test_apply_mapping__fixed_kind_keeps_the_whole_value(kind: str) -> None:
    mapping = mapping_of({"X": Suggest("issn_isbn", {"kind": kind})})
    value = "12345; 9783161484100; 1234-5678"

    assert getattr(apply_mapping({"X": value}, mapping), kind) == value


def test_apply_mapping__first_full_date_is_copied_as_it_is() -> None:
    mapping = mapping_of({"PY": "date", "DA": "date"})

    record = apply_mapping({"PY": " 2020/// ", "DA": "2019/03/15/"}, mapping)

    assert record.publication_date == "2020///"


def test_apply_mapping__full_date_wins_over_date_parts() -> None:
    mapping = mapping_of(
        {
            "Date": "date",
            "Year": Suggest("date", {"part": "year"}),
            "Month": Suggest("date", {"part": "month"}),
        }
    )

    record = apply_mapping(
        {"Date": "2019-01-05", "Year": "2020", "Month": "Mar"}, mapping
    )

    assert record.publication_date == "2019-01-05"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"Date": "", "Year": "2020", "Month": "Mar", "Day": "5"}, "2020/Mar/5"),
        ({"Year": "1994"}, "1994//"),
        ({"Month": "03"}, "/03/"),
        ({"Year": "n.d."}, "n.d.//"),
    ],
)
def test_apply_mapping__date_parts_are_joined_as_they_are(
    raw: dict[str, str], expected: str
) -> None:
    mapping = mapping_of(
        {
            "Date": "date",
            "Year": Suggest("date", {"part": "year"}),
            "Month": Suggest("date", {"part": "month"}),
            "Day": Suggest("date", {"part": "day"}),
        }
    )

    assert apply_mapping(raw, mapping).publication_date == expected


def test_apply_mapping__no_date_values_leave_no_date() -> None:
    mapping = mapping_of({"Date": "date", "Year": Suggest("date", {"part": "year"})})

    assert apply_mapping({"Date": " ", "Year": ""}, mapping).publication_date is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020///", (2020, None, None)),
        ("2020/05//", (2020, 5, None)),
        ("2020/05/14/", (2020, 5, 14)),
        ("2020/05/14/Spring", (2020, 5, 14)),
        ("2020///Spring", (2020, None, None)),
        ("2020 May 14", (2020, 5, 14)),
        ("2020 May", (2020, 5, None)),
        ("2020 Jan-Feb", (2020, 1, None)),
        ("2020 Oct 3", (2020, 10, 3)),
    ],
)
def test_parse_date_string__reads_ris_and_nbib_dates(
    value: str, expected: tuple[int, int | None, int | None]
) -> None:
    date = parse_date_string(value)

    assert date is not None
    assert (date.year, date.month, date.day) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1994//", (1994, None, None)),
        ("1994/03/", (1994, 3, None)),
        ("1994/Mar/", (1994, 3, None)),
        ("1994/3/5", (1994, 3, 5)),
        ("2020/03/04", (2020, 3, 4)),
    ],
)
def test_parse_date_string__reads_joined_date_parts(
    value: str, expected: tuple[int, int | None, int | None]
) -> None:
    date = parse_date_string(value, "us")

    assert date is not None
    assert (date.year, date.month, date.day) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("14/05/2020", (2020, 5, 14)),
        ("05/14/2020", (2020, 5, 14)),
        ("3.4.2020", (2020, 4, 3)),
        ("03-04-2020", (2020, 4, 3)),
        ("12 March 2020", (2020, 3, 12)),
        ("12 Mar. 2020", (2020, 3, 12)),
        ("March 12, 2020", (2020, 3, 12)),
        ("Oct2021", (2021, 10, None)),
        ("Oct 2021", (2021, 10, None)),
        ("October 2021", (2021, 10, None)),
        ("Fall2013", (2013, None, None)),
        ("autumn 2013", (2013, None, None)),
    ],
)
def test_parse_date_string__reads_day_month_and_named_forms(
    value: str, expected: tuple[int, int | None, int | None]
) -> None:
    date = parse_date_string(value)

    assert date is not None
    assert (date.year, date.month, date.day) == expected


def test_parse_date_string__ambiguous_numeric_date_defaults_to_eu_order() -> None:
    date = parse_date_string("03/04/2020")

    assert date is not None
    assert (date.month, date.day) == (4, 3)


def test_parse_date_string__ambiguous_numeric_date_uses_us_order() -> None:
    date = parse_date_string("03/04/2020", "us")

    assert date is not None
    assert (date.month, date.day) == (3, 4)


def test_parse_date_string__unambiguous_numeric_date_ignores_order() -> None:
    date = parse_date_string("14/05/2020", "us")

    assert date is not None
    assert (date.month, date.day) == (5, 14)


@pytest.mark.parametrize("value", ["13/14/2020", "03/04-2020"])
def test_parse_date_string__rejects_impossible_or_mixed_numeric_date(
    value: str,
) -> None:
    assert parse_date_string(value) is None


def test_apply_mapping__keeps_each_keyword_column_unsplit_under_its_prefix() -> None:
    mapping = mapping_of({"A": Suggest("keywords", {"prefix": "A"}), "B": "keywords"})

    record = apply_mapping({"A": "x; y", "B": "z|w"}, mapping)

    assert record.keywords == ["A:[x; y]", "keywords:[z|w]"]


def test_parse_unsplit_keywords__gives_prefix_and_value() -> None:
    assert parse_unsplit_keywords(unsplit_keywords("A", "x; y")) == ("A", "x; y")
    assert parse_unsplit_keywords(unsplit_keywords("", "z")) == ("", "z")
    assert parse_unsplit_keywords("[A] x") is None


@pytest.mark.parametrize("typed", ["Author", " Author ", "[Author]", "[Author] "])
def test_keywords_row__prefix_is_stored_without_brackets(typed: str) -> None:
    assert KeywordsRow(prefix=typed).prefix == "Author"


def test_tag_keyword__tags_keyword_only_with_a_prefix() -> None:
    assert tag_keyword("MeSH", "Humans") == "[MeSH] Humans"
    assert tag_keyword("", "Humans") == "Humans"


_PARALLEL = {
    "Author": Suggest("authors"),
    "ORCID": Suggest("authors", {"role": "ids", "id_key": "orcid"}),
    "Author IDs": Suggest("authors", {"role": "ids", "id_key": "openalex_author_id"}),
    "Affiliations": Suggest("authors", {"role": "affiliations"}),
}


def test_apply_mapping__keeps_names_and_affiliations_as_in_the_file() -> None:
    raw = {"Author": "Ann Lee|Bo Kim", "Affiliations": "Uni A| Uni B"}

    record = apply_mapping(raw, mapping_of(_PARALLEL))

    assert record.author_names == "Ann Lee|Bo Kim"
    assert record.author_affiliations == "Uni A| Uni B"
    assert record.author_ids is None


def test_apply_mapping__keeps_each_id_column_unsplit_under_its_key() -> None:
    raw = {"ORCID": " |https://orcid.org/0000-0001 ", "Author IDs": "A1|A2"}

    record = apply_mapping(raw, mapping_of(_PARALLEL))

    assert record.author_ids == (
        "orcid:[|https://orcid.org/0000-0001], openalex_author_id:[A1|A2]"
    )


def test_apply_mapping__first_non_empty_name_column_wins() -> None:
    mapping = mapping_of({"Full": "authors", "Short": "authors"})

    record = apply_mapping({"Full": "", "Short": "Teng Y.; Han Y."}, mapping)

    assert record.author_names == "Teng Y.; Han Y."


def test_apply_mapping__unmapped_author_columns_are_not_read() -> None:
    mapping = mapping_of({"Author": _PARALLEL["Author"]})

    record = apply_mapping({"Author": "Ann Lee", "Author IDs": "A1"}, mapping)

    assert (record.author_names, record.author_ids) == ("Ann Lee", None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("include", "include"),
        ("Included", "include"),
        (" YES ", "include"),
        ("y", "include"),
        ("1", "include"),
        ("true", "include"),
        ("relevant", "include"),
        ("exclude", "exclude"),
        ("Excluded", "exclude"),
        ("no", "exclude"),
        ("N", "exclude"),
        ("0", "exclude"),
        ("False", "exclude"),
        ("irrelevant", "exclude"),
        ("maybe", "maybe"),
        ("Unsure", "maybe"),
        ("undecided", "maybe"),
        ("?", "maybe"),
        ("", "unlabeled"),
        ("  ", "unlabeled"),
    ],
)
def test_normalize_label__maps_known_spellings(value: str, expected: str) -> None:
    assert normalize_label(value) == expected


def test_normalize_label__minus_one_is_unlabeled_unless_listed_elsewhere() -> None:
    settings = ParseSettings(label_values=(("-1", "exclude"),))

    assert normalize_label("-1") == "unlabeled"
    assert normalize_label("-1", settings) == "exclude"


_ASREVIEW_VALUES = ParseSettings(
    label_values=(("asreview_relevant", "include"), ("1", "exclude"))
)


def test_normalize_label__custom_value_overrides_builtin() -> None:
    assert normalize_label("1", _ASREVIEW_VALUES) == "exclude"
    assert normalize_label("0", _ASREVIEW_VALUES) == "exclude"


def test_normalize_label__custom_match_is_case_insensitive() -> None:
    assert normalize_label(" ASReview_Relevant ", _ASREVIEW_VALUES) == "include"


def test_normalize_label__multiline_first_match() -> None:
    value = "EID: 2-s2.0-1\nASReview_relevant\nirrelevant"

    assert normalize_label(value, _ASREVIEW_VALUES) == "include"


def test_normalize_label__multiline_no_match_is_unlabeled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        value = normalize_label("EID: 2-s2.0-1\nExport Date: 22 October 2026")

    assert value == "unlabeled"
    assert caplog.text == ""


def test_normalize_label__single_line_unmatched_is_unknown() -> None:
    assert normalize_label("asreview_not_seen", _ASREVIEW_VALUES) == "unknown"


def test_normalize_label__unknown_spelling_is_unknown_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        value = normalize_label("conflict")

    assert value == "unknown"
    assert "conflict" in caplog.text


def test_apply_mapping__label_uses_phase_and_screener() -> None:
    mapping = mapping_of(
        {"included": Suggest("label", {"phase": "tiab", "screener": "Emily"})}
    )

    record = apply_mapping({"included": "1"}, mapping)

    assert record.labels == [Label(phase="tiab", screener="Emily", value="include")]


def test_apply_mapping__label_defaults_to_ft_and_screener_1() -> None:
    record = apply_mapping({"included": "0"}, mapping_of({"included": "label"}))

    assert record.labels == [Label(phase="ft", screener="screener 1", value="exclude")]


def test_apply_mapping__empty_label_cell_is_unlabeled() -> None:
    record = apply_mapping({"included": ""}, mapping_of({"included": "label"}))

    assert [label.value for label in record.labels] == ["unlabeled"]


def test_apply_mapping__missing_label_cell_is_unlabeled() -> None:
    record = apply_mapping({}, mapping_of({"included": "label"}))

    assert [label.value for label in record.labels] == ["unlabeled"]


def test_apply_mapping__several_label_columns_keep_mapping_order() -> None:
    mapping = mapping_of(
        {
            "TiAb": Suggest("label", {"phase": "tiab"}),
            "FT": Suggest("label", {"phase": "ft"}),
        }
    )

    record = apply_mapping({"TiAb": "Included", "FT": "maybe"}, mapping)

    assert [(label.phase, label.value) for label in record.labels] == [
        ("tiab", "include"),
        ("ft", "maybe"),
    ]


def _targets(mapping: FieldMapping) -> dict[str, str]:
    return {key: row.target for key, row in mapping.rows.items()}


def test_suggest_mapping__strict_matches_exact_aliases_only() -> None:
    suggestions = {"ti": Suggest("title"), "do": Suggest("doi")}

    mapping = suggest_mapping(["TI", "tj", "Custom ID"], suggestions, lenient=False)

    assert _targets(mapping) == {"TI": "title"}


def test_suggest_mapping__builds_rows_with_suggested_options() -> None:
    suggestions = {"pmcid": Suggest("other_ids", {"key": "pmc"})}

    mapping = suggest_mapping(["PMCID"], suggestions, lenient=True)

    assert mapping.rows == {"PMCID": OtherIdRow(key="pmc")}


def test_suggest_mapping__several_keys_may_share_a_target() -> None:
    suggestions = {"da": Suggest("date"), "py": Suggest("date")}

    mapping = suggest_mapping(["PY", "DA"], suggestions, lenient=False)

    assert _targets(mapping) == {"PY": "date", "DA": "date"}


def test_suggest_mapping__records_match_kind_per_key() -> None:
    suggestions = {"article title": Suggest("title"), "doi": Suggest("doi")}

    mapping = suggest_mapping(
        ["DOI", "Article Titles", "Custom ID", "Zzzqqqxx123"],
        suggestions,
        lenient=True,
    )

    assert mapping.match_kinds == {
        "DOI": "exact",
        "Article Titles": "fuzzy",
        "Custom ID": "id_fallback",
    }


def test_suggest_mapping__lenient_fuzzy_matches_and_falls_back_to_id() -> None:
    suggestions = {"article title": Suggest("title")}

    mapping = suggest_mapping(
        ["Article Titles", "Custom ID"], suggestions, lenient=True
    )

    assert mapping.rows == {
        "Article Titles": ScalarRow(target="title"),
        "Custom ID": OtherIdRow(key="custom_id"),
    }


def test_override_aliases__drops_base_aliases_of_an_overridden_target() -> None:
    base = {"jt": Suggest("journal"), "ta": Suggest("journal"), "ti": Suggest("title")}

    merged = override_aliases(base, {"jt": Suggest("journal")})

    assert merged == {"ti": Suggest("title"), "jt": Suggest("journal")}


def test_override_aliases__moves_alias_to_a_new_target() -> None:
    base = {"type": Suggest("notes"), "ty": Suggest("publication_type")}

    merged = override_aliases(base, {"type": Suggest("publication_type")})

    assert merged == {"type": Suggest("publication_type")}


def test_split_keyword__splits_prefix_off() -> None:
    assert split_keyword("[MeSH] Humans") == ("MeSH", "Humans")


def test_split_keyword__unprefixed_keyword() -> None:
    assert split_keyword("Humans") == (None, "Humans")


def test_split_keyword__round_trips_tagged() -> None:
    assert split_keyword(tag_keyword("Author", "[a] b")) == ("Author", "[a] b")
