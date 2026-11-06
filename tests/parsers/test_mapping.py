import logging

import pytest
from pydantic import ValidationError

from app.models.record import Affiliation, Author, Label
from app.parsers.mapping import (
    AuthorsRow,
    DateRow,
    FieldMapping,
    IssnIsbnRow,
    KeywordsRow,
    LabelRow,
    OtherIdRow,
    PagesRow,
    RowDefaults,
    ScalarRow,
    Suggest,
    apply_mapping,
    default_row,
    is_ambiguous_date,
    make_row,
    normalize_label,
    override_aliases,
    parse_date_string,
    suggest_mapping,
)
from app.parsers.quirks import ParseSettings
from tests.mappings import mapping_of

_DEFAULTS = RowDefaults()


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
    defaults = RowDefaults(delimiter="|", date_order="us")

    assert default_row("title", "TI", defaults) == ScalarRow(target="title")
    assert default_row("date", "DA", defaults) == DateRow(part="full", order="us")
    assert default_row("pages", "PG", defaults) == PagesRow(part="range")
    assert default_row("issn_isbn", "SN", defaults) == IssnIsbnRow(kind="auto")
    assert default_row("other_ids", "Work ID", defaults) == OtherIdRow(key="work_id")
    assert default_row("authors", "Author IDs", defaults) == AuthorsRow(
        role="last_first", delimiter="|", separator=",", id_key="author_ids"
    )
    assert default_row("keywords", "KW", defaults) == KeywordsRow(delimiter="|")
    assert default_row("label", "L", defaults) == LabelRow(
        phase="ft", screener="screener 1"
    )


def test_default_row__author_delimiter_overrides_list_delimiter() -> None:
    defaults = RowDefaults(author_delimiter="\n")

    authors = default_row("authors", "author", defaults)
    keywords = default_row("keywords", "keywords", defaults)

    assert isinstance(authors, AuthorsRow) and authors.delimiter == "\n"
    assert isinstance(keywords, KeywordsRow) and keywords.delimiter == ";"


def test_default_row__rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="unknown Record field"):
        default_row("not_a_field", "X", _DEFAULTS)


def test_make_row__applies_suggested_options_over_defaults() -> None:
    row = make_row(Suggest("authors", {"role": "orcid"}), "ORCID", _DEFAULTS)

    assert row == AuthorsRow(role="orcid", delimiter=";", id_key="orcid")


def test_make_row__rejects_invalid_option() -> None:
    with pytest.raises(ValidationError):
        make_row(Suggest("date", {"part": "week"}), "DA", _DEFAULTS)


def test_apply_mapping__first_non_empty_value_wins_for_scalar() -> None:
    mapping = mapping_of({"A": "title", "B": "title", "C": "title"})

    record = apply_mapping({"A": "", "B": "First", "C": "Second"}, mapping)

    assert record.title == "First"


def test_apply_mapping__empty_values_use_next_mapped_key() -> None:
    mapping = mapping_of({"TI": "title", "TT": "title"})
    settings = ParseSettings(empty_values=("[Not Available].",))
    raw = {"TI": " [not available]. ", "TT": "Translated"}

    assert apply_mapping(raw, mapping, settings).title == "Translated"
    assert apply_mapping({"TI": "[Not Available]."}, mapping, settings).title is None


def test_apply_mapping__empty_values_apply_to_every_text_field() -> None:
    mapping = mapping_of({"TI": "title", "JO": "journal", "DO": "doi"})
    settings = ParseSettings(empty_values=("n/a",))

    record = apply_mapping(
        {"TI": "N/A", "JO": "n/a", "DO": "10.1/x"}, mapping, settings
    )

    assert (record.title, record.journal, record.doi) == (None, None, "10.1/x")


def test_apply_mapping__empty_values_match_the_whole_value() -> None:
    mapping = mapping_of({"TI": "title"})
    settings = ParseSettings(empty_values=("[Not Available].",))

    record = apply_mapping({"TI": "[Not Available]. A title"}, mapping, settings)

    assert record.title == "[Not Available]. A title"


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

    assert [a.given_name for a in record.authors] == ["Jane"]


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


_ONLY_ONE = ParseSettings(issn_isbn_only_one=True)
_STRIP = ParseSettings(issn_isbn_strip_extras=True)
_BOTH = ParseSettings(issn_isbn_strip_extras=True, issn_isbn_only_one=True)


def test_apply_mapping__issn_isbn_splits_issn_and_isbn() -> None:
    record = apply_mapping({"SN": "1234-5678; 9783161484100"}, _SN, _BOTH)

    assert (record.issn, record.isbn) == ("1234-5678", "9783161484100")


@pytest.mark.parametrize(
    "value", ["1234-5678 8765-4321", "1234-5678|8765-4321", "1234-5678\n8765-4321"]
)
def test_apply_mapping__issn_isbn_only_one_keeps_first_value(value: str) -> None:
    assert apply_mapping({"SN": value}, _SN, _BOTH).issn == "1234-5678"


def test_apply_mapping__issn_isbn_strip_extras_keeps_all_values_without_only_one() -> (
    None
):
    value = "1234-5678 (electronic), 9123-4567 (print)"

    record = apply_mapping({"SN": value}, _SN, _STRIP)

    assert record.issn == "1234-5678; 9123-4567"


def test_apply_mapping__issn_isbn_both_off_keeps_raw_value() -> None:
    value = "1234-5678 (electronic), 9123-4567 (print)"

    assert apply_mapping({"SN": value}, _SN).issn == value


def test_apply_mapping__issn_isbn_only_one_without_strip_keeps_qualifier() -> None:
    value = "1234-5678 (electronic), 9123-4567 (print)"

    assert apply_mapping({"SN": value}, _SN, _ONLY_ONE).issn == (
        "1234-5678 (electronic)"
    )


def test_apply_mapping__issn_isbn_unrecognised_value_goes_to_issn_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        record = apply_mapping({"SN": "12345"}, _SN, _BOTH)

    assert (record.issn, record.isbn) == ("12345", None)
    assert "12345" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("23330937 (ISSN)", ("23330937", None)),
        ("979-840072171-7 (ISBN)", (None, "979-840072171-7")),
        ("(Print) 1234-5678", ("1234-5678", None)),
    ],
)
def test_apply_mapping__issn_isbn_strip_extras_drops_qualifier(
    value: str,
    expected: tuple[str | None, str | None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        record = apply_mapping({"SN": value}, _SN, _STRIP)

    assert (record.issn, record.isbn) == expected
    assert caplog.text == ""


def test_apply_mapping__issn_isbn_both_off_routes_raw_value_by_its_first_id() -> None:
    record = apply_mapping({"SN": "979-840072171-7 (ISBN)"}, _SN)

    assert (record.issn, record.isbn) == (None, "979-840072171-7 (ISBN)")


def test_apply_mapping__issn_isbn_empty_value_sets_nothing() -> None:
    record = apply_mapping({"SN": "  "}, _SN, _BOTH)

    assert (record.issn, record.isbn) == (None, None)


@pytest.mark.parametrize("kind", ["issn", "isbn"])
def test_apply_mapping__fixed_kind_takes_first_id_whatever_its_length(
    kind: str,
) -> None:
    mapping = mapping_of({"X": Suggest("issn_isbn", {"kind": kind})})

    record = apply_mapping({"X": "12345; 9783161484100; 1234-5678"}, mapping, _BOTH)

    assert getattr(record, kind) == "9783161484100"


def test_apply_mapping__fixed_kind_unrecognised_value_is_kept() -> None:
    mapping = mapping_of({"ISSN": Suggest("issn_isbn", {"kind": "issn"})})

    assert apply_mapping({"ISSN": "12345"}, mapping, _BOTH).issn == "12345"


_IS_LINES = "1234-5678 (Print)\n8765-4321 (Electronic)\n1234-5678 (Linking)"
_IS = mapping_of({"IS": Suggest("issn_isbn", {"kind": "issn"})})


@pytest.mark.parametrize("preferred", ["Electronic", "electronic", " ELECTRONIC "])
def test_apply_mapping__preferred_qualifier_value_wins(preferred: str) -> None:
    settings = ParseSettings(
        issn_isbn_strip_extras=True,
        issn_isbn_only_one=True,
        preferred_issn_qualifier=preferred,
    )

    assert apply_mapping({"IS": _IS_LINES}, _IS, settings).issn == "8765-4321"


def test_apply_mapping__without_preferred_qualifier_first_value_wins() -> None:
    assert apply_mapping({"IS": _IS_LINES}, _IS, _BOTH).issn == "1234-5678"


def test_apply_mapping__unmatched_preferred_qualifier_keeps_first_value() -> None:
    settings = ParseSettings(
        issn_isbn_strip_extras=True,
        issn_isbn_only_one=True,
        preferred_issn_qualifier="Online",
    )

    assert apply_mapping({"IS": _IS_LINES}, _IS, settings).issn == "1234-5678"


def test_apply_mapping__preferred_qualifier_is_ignored_without_only_one() -> None:
    settings = ParseSettings(
        issn_isbn_strip_extras=True, preferred_issn_qualifier="Electronic"
    )

    assert apply_mapping({"IS": _IS_LINES}, _IS, settings).issn == (
        "1234-5678; 8765-4321; 1234-5678"
    )


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
    date = apply_mapping({"DA": value}, mapping_of({"DA": "date"})).publication_date

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
    date = apply_mapping({"DP": value}, mapping_of({"DP": "date"})).publication_date

    assert date is not None
    assert (date.year, date.month, date.day) == expected


def test_apply_mapping__date_order_comes_from_the_row() -> None:
    mapping = mapping_of({"Date": Suggest("date", {"order": "us"})})

    date = apply_mapping({"Date": "03/04/2020"}, mapping).publication_date

    assert date is not None
    assert (date.month, date.day) == (3, 4)


def test_apply_mapping__full_dates_combine_per_part_first_wins() -> None:
    mapping = mapping_of({"PY": "date", "DA": "date"})

    date = apply_mapping({"PY": "2020///", "DA": "2019/03/15/"}, mapping)

    assert date.publication_date is not None
    assert date.publication_date.model_dump() == {"year": 2020, "month": 3, "day": 15}


def test_apply_mapping__date_part_rows_win_over_full_date() -> None:
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

    assert record.publication_date is not None
    assert record.publication_date.model_dump() == {"year": 2020, "month": 3, "day": 5}


def test_apply_mapping__unparseable_year_part_is_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mapping = mapping_of({"Year": Suggest("date", {"part": "year"})})

    with caplog.at_level(logging.WARNING):
        record = apply_mapping({"Year": "n.d."}, mapping)

    assert record.publication_date is None
    assert "n.d." in caplog.text


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("03/04/2020", True),
        (" 3.4.2020 ", True),
        ("03/03/2020", False),
        ("14/05/2020", False),
        ("2020-03-04", False),
        ("March 4, 2020", False),
    ],
)
def test_is_ambiguous_date__only_when_order_changes_the_date(
    value: str, expected: bool
) -> None:
    assert is_ambiguous_date(value) is expected


def test_apply_mapping__keywords_use_row_delimiter_and_prefix() -> None:
    mapping = mapping_of(
        {
            "A": Suggest("keywords", {"prefix": "A"}),
            "B": Suggest("keywords", {"delimiter": "|"}),
        }
    )

    record = apply_mapping({"A": "x; y", "B": "z|w"}, mapping)

    assert record.keywords == ["[A] x", "[A] y", "z", "w"]


@pytest.mark.parametrize("typed", ["Author", " Author ", "[Author]", "[Author] "])
def test_keywords_row__prefix_is_stored_without_brackets(typed: str) -> None:
    assert KeywordsRow(delimiter=";", prefix=typed).prefix == "Author"


def test_keywords_row__tags_keyword_only_with_a_prefix() -> None:
    assert KeywordsRow(delimiter=";", prefix="MeSH").tagged("Humans") == "[MeSH] Humans"
    assert KeywordsRow(delimiter=";").tagged("Humans") == "Humans"


def test_apply_mapping__name_roles_split_names() -> None:
    raw = {"A": "Smith, John; Doe, Jane", "B": "John Smith", "C": "Smith, John"}

    def names(role: str, key: str) -> list[tuple[str | None, str | None]]:
        separator = " " if role == "first_last" else ","
        mapping = mapping_of(
            {key: Suggest("authors", {"role": role, "separator": separator})}
        )
        authors = apply_mapping(raw, mapping).authors
        return [(a.family_name, a.given_name) for a in authors]

    assert names("last_first", "A") == [("Smith", "John"), ("Doe", "Jane")]
    assert names("first_last", "B") == [("Smith", "John")]
    assert names("full_name", "C") == [(None, None)]


def test_apply_mapping__ambiguous_name_follows_settings() -> None:
    mapping = mapping_of({"AU": "authors"})
    raw = {"AU": "Smith, Jr., John"}

    unsplit = apply_mapping(raw, mapping).authors[0]
    split = apply_mapping(
        raw, mapping, ParseSettings(ambiguous_name_split="last")
    ).authors[0]

    assert unsplit.family_name is None
    assert (split.family_name, split.given_name) == ("Smith, Jr.", "John")


_PARALLEL = {
    "Author": Suggest("authors", {"role": "full_name", "delimiter": "|"}),
    "ORCID": Suggest("authors", {"role": "orcid", "delimiter": "|"}),
    "Author IDs": Suggest(
        "authors", {"role": "ids", "delimiter": "|", "id_key": "openalex_author_id"}
    ),
    "Affiliations": Suggest("authors", {"role": "affiliations", "delimiter": "|"}),
}


def test_apply_mapping__zips_parallel_author_columns() -> None:
    raw = {
        "Author": "Ann Lee|Bo Kim",
        "ORCID": "|https://orcid.org/0000-0001-2345-6789",
        "Author IDs": "A1|A2",
        "Affiliations": "Uni A|",
    }

    record = apply_mapping(raw, mapping_of(_PARALLEL))

    assert record.authors == [
        Author(
            full_name="Ann Lee",
            other_ids={"openalex_author_id": "A1"},
            affiliations=[Affiliation(name="Uni A")],
        ),
        Author(
            full_name="Bo Kim",
            orcid="0000-0001-2345-6789",
            other_ids={"openalex_author_id": "A2"},
        ),
    ]


def test_apply_mapping__first_non_empty_name_column_wins() -> None:
    mapping = mapping_of({"Full": "authors", "Short": "authors"})

    record = apply_mapping({"Full": "", "Short": "Teng Y.; Han Y."}, mapping)

    assert [a.full_name for a in record.authors] == ["Teng Y.", "Han Y."]


def test_apply_mapping__ids_without_names_give_id_only_authors() -> None:
    record = apply_mapping({"Author IDs": "A1|A2"}, mapping_of(_PARALLEL))

    assert record.authors == [
        Author(other_ids={"openalex_author_id": "A1"}),
        Author(other_ids={"openalex_author_id": "A2"}),
    ]


def test_apply_mapping__ignores_misaligned_author_column_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = {"Author": "Ann Lee|Bo Kim", "Author IDs": "A1|A2|A3"}

    with caplog.at_level(logging.WARNING):
        record = apply_mapping(raw, mapping_of(_PARALLEL))

    assert [a.other_ids for a in record.authors] == [{}, {}]
    assert "'Author IDs' has 3 entries for 2 authors" in caplog.text


def test_apply_mapping__drops_fully_empty_authors() -> None:
    record = apply_mapping({"Author": "Ann Lee||Bo Kim"}, mapping_of(_PARALLEL))

    assert [a.full_name for a in record.authors] == ["Ann Lee", "Bo Kim"]


def test_apply_mapping__unmapped_author_columns_are_not_read() -> None:
    mapping = mapping_of({"Author": _PARALLEL["Author"]})

    record = apply_mapping({"Author": "Ann Lee", "Author IDs": "A1"}, mapping)

    assert record.authors == [Author(full_name="Ann Lee")]


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

    mapping = suggest_mapping(
        ["TI", "tj", "Custom ID"], suggestions, _DEFAULTS, lenient=False
    )

    assert _targets(mapping) == {"TI": "title"}


def test_suggest_mapping__builds_rows_with_suggested_options() -> None:
    suggestions = {"pmcid": Suggest("other_ids", {"key": "pmc"})}

    mapping = suggest_mapping(["PMCID"], suggestions, _DEFAULTS, lenient=True)

    assert mapping.rows == {"PMCID": OtherIdRow(key="pmc")}


def test_suggest_mapping__several_keys_may_share_a_target() -> None:
    suggestions = {"da": Suggest("date"), "py": Suggest("date")}

    mapping = suggest_mapping(["PY", "DA"], suggestions, _DEFAULTS, lenient=False)

    assert _targets(mapping) == {"PY": "date", "DA": "date"}


def test_suggest_mapping__uses_row_defaults() -> None:
    defaults = RowDefaults(delimiter="\n")

    mapping = suggest_mapping(
        ["KW"], {"kw": Suggest("keywords")}, defaults, lenient=False
    )

    assert mapping.rows == {"KW": KeywordsRow(delimiter="\n")}


def test_suggest_mapping__records_match_kind_per_key() -> None:
    suggestions = {"article title": Suggest("title"), "doi": Suggest("doi")}

    mapping = suggest_mapping(
        ["DOI", "Article Titles", "Custom ID", "Zzzqqqxx123"],
        suggestions,
        _DEFAULTS,
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
        ["Article Titles", "Custom ID"], suggestions, _DEFAULTS, lenient=True
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
