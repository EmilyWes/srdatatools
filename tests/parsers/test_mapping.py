import pytest

from app.models.record import Label
from app.parsers.mapping import (
    SCALAR_FIELDS,
    FieldMapping,
    apply_mapping,
    normalize_label,
    override_aliases,
    suggest_mapping,
)
from app.parsers.quirks import ContinueToNextField, ParseSettings


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


def test_field_mapping__accepts_issn_isbn_target() -> None:
    mapping = FieldMapping(targets={"SN": "issn_isbn"})

    assert mapping.targets == {"SN": "issn_isbn"}


@pytest.mark.parametrize("value", ["1234-5678", "12345678", "1234-567X"])
def test_apply_mapping__issn_isbn_routes_issn(value: str) -> None:
    record = apply_mapping({"SN": value}, FieldMapping(targets={"SN": "issn_isbn"}))

    assert (record.issn, record.isbn) == (value, None)


@pytest.mark.parametrize(
    "value",
    ["0-306-40615-2", "0306406152", "978-3-16-148410-0", "9783161484100"],
)
def test_apply_mapping__issn_isbn_routes_isbn(value: str) -> None:
    record = apply_mapping({"SN": value}, FieldMapping(targets={"SN": "issn_isbn"}))

    assert (record.issn, record.isbn) == (None, value)


def test_apply_mapping__issn_isbn_splits_multiple_values() -> None:
    mapping = FieldMapping(targets={"SN": "issn_isbn"})

    record = apply_mapping({"SN": "1234-5678; 9783161484100"}, mapping)

    assert (record.issn, record.isbn) == ("1234-5678", "9783161484100")


def test_apply_mapping__issn_isbn_keeps_first_of_each_kind() -> None:
    mapping = FieldMapping(targets={"SN": "issn_isbn"})

    record = apply_mapping({"SN": "1234-5678 8765-4321"}, mapping)

    assert record.issn == "1234-5678"


def test_apply_mapping__issn_isbn_unrecognised_value_goes_to_issn_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mapping = FieldMapping(targets={"SN": "issn_isbn"})

    with caplog.at_level("WARNING"):
        record = apply_mapping({"SN": "12345"}, mapping)

    assert (record.issn, record.isbn) == ("12345", None)
    assert "12345" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("23330937 (ISSN)", ("23330937", None)),
        ("979-840072171-7 (ISBN)", (None, "979-840072171-7")),
    ],
)
def test_apply_mapping__issn_isbn_skips_parenthesised_qualifier_when_on(
    value: str,
    expected: tuple[str | None, str | None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    mapping = FieldMapping(targets={"SN": "issn_isbn"})

    with caplog.at_level("WARNING"):
        record = apply_mapping(
            {"SN": value}, mapping, ParseSettings(skip_issn_isbn_qualifiers=True)
        )

    assert (record.issn, record.isbn) == expected
    assert caplog.text == ""


def test_apply_mapping__issn_isbn_keeps_qualifier_when_off() -> None:
    mapping = FieldMapping(targets={"SN": "issn_isbn"})

    record = apply_mapping({"SN": "979-840072171-7 (ISBN)"}, mapping)

    assert (record.issn, record.isbn) == ("(ISBN)", "979-840072171-7")


def test_apply_mapping__issn_isbn_empty_value_sets_nothing() -> None:
    record = apply_mapping({"SN": "  "}, FieldMapping(targets={"SN": "issn_isbn"}))

    assert (record.issn, record.isbn) == (None, None)


def test_suggest_mapping__strict_matches_exact_aliases_only() -> None:
    aliases = {"title": ["ti"], "doi": ["do"]}

    suggestions = suggest_mapping(["TI", "tj", "Custom ID"], aliases, lenient=False)

    assert suggestions.targets == {"TI": "title"}


def test_suggest_mapping__alias_may_target_a_named_other_id() -> None:
    aliases = {"other_ids.pmc": ["pmcid"]}

    suggestions = suggest_mapping(["PMCID"], aliases, lenient=True)

    assert suggestions.targets == {"PMCID": "other_ids.pmc"}


def test_override_aliases__replaces_alias_list_of_overridden_target() -> None:
    merged = override_aliases({"journal": ["jt", "ta"]}, {"journal": ["jt"]})

    assert merged == {"journal": ["jt"]}


def test_override_aliases__moves_alias_away_from_its_old_target() -> None:
    merged = override_aliases({"other_ids": ["pmc", "mid"]}, {"other_ids.pmc": ["pmc"]})

    assert merged == {"other_ids": ["mid"], "other_ids.pmc": ["pmc"]}


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


def test_suggest_mapping__records_match_kind_per_key() -> None:
    aliases = {"title": ["article title"], "doi": ["doi"]}

    suggestions = suggest_mapping(
        ["DOI", "Article Titles", "Custom ID", "Zzzqqqxx123"], aliases, lenient=True
    )

    assert suggestions.match_kinds == {
        "DOI": "exact",
        "Article Titles": "fuzzy",
        "Custom ID": "id_fallback",
    }


def test_suggest_mapping__dropped_exclusive_loser_has_no_match_kind() -> None:
    aliases = {"date": ["da", "py"]}

    suggestions = suggest_mapping(["PY", "DA"], aliases, lenient=False)

    assert suggestions.match_kinds == {"DA": "exact"}


def test_suggest_mapping__lenient_fuzzy_matches_and_falls_back_to_id() -> None:
    aliases = {"title": ["article title"]}

    suggestions = suggest_mapping(
        ["Article Titles", "Custom ID"], aliases, lenient=True
    )

    assert suggestions.targets == {
        "Article Titles": "title",
        "Custom ID": "other_ids.custom_id",
    }


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


def test_normalize_label__minus_one_is_unlabeled_only_when_on() -> None:
    assert normalize_label("-1", minus_one_unlabeled=True) == "unlabeled"
    assert normalize_label("-1") == "unknown"


def test_apply_mapping__continue_to_next_field_uses_next_mapped_key() -> None:
    mapping = FieldMapping(targets={"TI": "title", "TT": "title"})
    settings = ParseSettings(
        continue_to_next=(
            ContinueToNextField("title", frozenset({"[Not Available]."}), True),
        )
    )
    raw = {"TI": "[Not Available].", "TT": "Translated"}

    assert apply_mapping(raw, mapping, settings).title == "Translated"
    assert apply_mapping({"TI": "[Not Available]."}, mapping, settings).title is None


def test_apply_mapping__keyword_prefix_applies_per_key() -> None:
    mapping = FieldMapping(targets={"A": "keywords", "B": "keywords"})
    settings = ParseSettings(keyword_prefixes={"A": "[A] "})

    record = apply_mapping({"A": "x; y", "B": "z"}, mapping, settings)

    assert record.keywords == ["[A] x", "[A] y", "z"]


def test_normalize_label__unknown_spelling_is_unknown_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        value = normalize_label("conflict")

    assert value == "unknown"
    assert "conflict" in caplog.text


def test_field_mapping__allows_label_target_from_several_inputs() -> None:
    mapping = FieldMapping(targets={"TiAb": "label", "FT": "label"})

    assert mapping.targets == {"TiAb": "label", "FT": "label"}


def test_apply_mapping__label_uses_phase_and_screener() -> None:
    mapping = FieldMapping(
        targets={"included": "label"},
        label_phases={"included": "tiab"},
        label_screeners={"included": "Emily"},
    )

    record = apply_mapping({"included": "1"}, mapping)

    assert record.labels == [Label(phase="tiab", screener="Emily", value="include")]


def test_apply_mapping__label_falls_back_to_default_phase_and_screener() -> None:
    mapping = FieldMapping(
        targets={"included": "label"},
        label_phases={"included": "  "},
    )

    record = apply_mapping({"included": "0"}, mapping)

    assert record.labels == [Label(phase="ft", screener="screener 1", value="exclude")]


def test_apply_mapping__empty_label_cell_is_unlabeled() -> None:
    mapping = FieldMapping(targets={"included": "label"})

    record = apply_mapping({"included": ""}, mapping)

    assert [label.value for label in record.labels] == ["unlabeled"]


def test_apply_mapping__missing_label_cell_is_unlabeled() -> None:
    record = apply_mapping({}, FieldMapping(targets={"included": "label"}))

    assert [label.value for label in record.labels] == ["unlabeled"]


def test_apply_mapping__several_label_columns_keep_mapping_order() -> None:
    mapping = FieldMapping(
        targets={"TiAb": "label", "FT": "label"},
        label_phases={"TiAb": "tiab", "FT": "ft"},
    )

    record = apply_mapping({"TiAb": "Included", "FT": "maybe"}, mapping)

    assert [(label.phase, label.value) for label in record.labels] == [
        ("tiab", "include"),
        ("ft", "maybe"),
    ]
