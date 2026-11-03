import pytest

from app.parsers.profiles import PROFILES, profile_for
from app.parsers.profiles.overview import (
    QuirkChoice,
    QuirkEntry,
    dump_choices,
    load_choices,
    profile_with,
    quirk_entries,
)
from app.parsers.quirks import (
    AffiliationLeadingName,
    DropEtAl,
    EmbeddedAuthorIds,
    FirstValue,
    StripLastAuthorTrailing,
)

_ALL_TYPES = ("ris", "nbib", "csv", "tsv", "excel", "bibtex")


def _entries(file_type: str, source: str = "unknown") -> dict[str, QuirkEntry]:
    return {entry.key: entry for entry in quirk_entries(file_type, source)}


def _choices(entries: dict[str, QuirkEntry]) -> dict[str, QuirkChoice]:
    return {key: entry.default.model_copy(deep=True) for key, entry in entries.items()}


@pytest.mark.parametrize("source", ["unknown", *PROFILES], ids=["unknown", *PROFILES])
@pytest.mark.parametrize("file_type", _ALL_TYPES)
def test_profile_with__defaults_reproduce_the_profile(
    file_type: str, source: str
) -> None:
    profile = profile_for(source, file_type)

    assert profile_with(file_type, source, {}) == profile
    assert profile_with(file_type, source, _choices(_entries(file_type, source))) == (
        profile
    )


def test_quirk_entries__column_types_list_every_column_profile_quirk() -> None:
    for file_type in ("csv", "tsv", "excel"):
        entries = _entries(file_type)

        assert entries["DropEtAl"].default.on
        assert entries["FirstValue.issn"].default.on
        assert not entries["EmbeddedAuthorIds"].default.on
        assert not entries["AffiliationLeadingName"].default.on
        assert not entries["StripLastAuthorTrailing"].default.on


def test_quirk_entries__field_size_limit_only_for_csv_and_tsv() -> None:
    assert _entries("csv")["csv_field_size_limit"].kind == "setting"
    assert "csv_field_size_limit" in _entries("tsv")
    assert "csv_field_size_limit" not in _entries("excel")
    assert "csv_field_size_limit" not in _entries("ris")


def test_quirk_entries__parser_behaviours_per_type() -> None:
    assert _entries("ris")["ris.author_details"].kind == "parser"
    assert _entries("bibtex")["bibtex.key_continuation"].kind == "parser"
    assert "ris.author_details" not in _entries("bibtex")
    for file_type in ("csv", "tsv", "excel", "bibtex"):
        assert _entries(file_type)["author_columns"].kind == "parser"
    assert "author_columns" not in _entries("ris")
    assert "author_columns" not in _entries("nbib")


def test_quirk_entries__origins() -> None:
    entries = _entries("csv")

    for key in (
        "skip_issn_isbn_qualifiers",
        "FirstValue.isbn",
        "FirstValue.issn",
        "DropEtAl",
        "StripPrefix.pmid",
        "ExpandPageRange",
        "ContinueToNextField.title",
    ):
        assert entries[key].origin == "general"
    assert entries["csv_field_size_limit"].origin == "type"
    assert entries["EmbeddedAuthorIds"].origin == "general"
    assert _entries("nbib")["FirstValue.publication_type"].origin == "type"
    assert _entries("ris")["RisNotes"].origin == "general"


def test_quirk_entries__used_by_names_the_declaring_profiles() -> None:
    entries = _entries("tsv")

    assert entries["EmbeddedAuthorIds"].used_by == ("Scopus",)
    assert entries["StripLastAuthorTrailing"].used_by == ("PubMed",)
    assert entries["DropEtAl"].used_by == ()


def test_quirk_entries__selected_profile_turns_its_own_quirks_on() -> None:
    entries = _entries("csv", "scopus")

    assert entries["EmbeddedAuthorIds"].default.on
    assert entries["EmbeddedAuthorIds"].default.values == {"id_key": "scopus_author_id"}
    assert entries["DropEtAl"].default.on
    assert not entries["StripLastAuthorTrailing"].default.on


def test_quirk_entries__nbib_prefers_electronic_issn() -> None:
    entry = _entries("nbib")["skip_issn_isbn_qualifiers"]

    assert entry.default == QuirkChoice(on=True, values={"preferred": "Electronic"})
    assert _entries("csv")["skip_issn_isbn_qualifiers"].default.values == {
        "preferred": ""
    }


def test_quirk_entries__first_isbn_and_issn_have_an_editable_delimiter() -> None:
    entries = _entries("ris")

    assert entries["FirstValue.isbn"].default.values == {"delimiter": "\n"}
    assert entries["FirstValue.issn"].default.values == {"delimiter": "|"}
    assert entries["FirstValue.isbn"].details == ()
    assert not entries["FirstValue.isbn"].options[0].strip


def test_quirk_entries__first_publication_type_line_delimiter_is_read_only() -> None:
    entry = _entries("nbib")["FirstValue.publication_type"]

    assert entry.options == ()
    assert entry.details == ("Delimiter: new line",)


def test_quirk_entries__url_pattern_is_read_only() -> None:
    eid = _entries("bibtex")["IdFromUrl"]

    assert [option.name for option in eid.options] == ["id_key", "prefix"]
    assert eid.details[0] == "Input key: 'url'"
    assert eid.details[1].startswith("URL pattern: scopus")


def test_quirk_entries__unsupported_type_raises() -> None:
    with pytest.raises(ValueError):
        quirk_entries("unknown", "unknown")


def test_profile_with__turns_a_type_default_off() -> None:
    choices = {"DropEtAl": QuirkChoice(on=False)}

    profile = profile_with("csv", "unknown", choices)

    assert DropEtAl() not in profile.quirks


def test_profile_with__turns_another_profiles_quirk_on_with_its_arguments() -> None:
    choices = {
        "EmbeddedAuthorIds": QuirkChoice(on=True, values={"id_key": "my_id"}),
        "AffiliationLeadingName": QuirkChoice(on=True, values={"separator": "; "}),
    }

    profile = profile_with("excel", "unknown", choices)

    assert EmbeddedAuthorIds("my_id") in profile.quirks
    assert AffiliationLeadingName("; ") in profile.quirks


def test_profile_with__edits_a_delimiter() -> None:
    choices = {"FirstValue.issn": QuirkChoice(on=True, values={"delimiter": ";"})}

    profile = profile_with("csv", "openalex", choices)

    assert FirstValue("issn", ";") in profile.quirks
    assert FirstValue("issn", "|") not in profile.quirks


def test_profile_with__keeps_declaration_order() -> None:
    choices = {"StripLastAuthorTrailing": QuirkChoice(on=True, values={"chars": "."})}

    quirks = profile_with("tsv", "unknown", choices).quirks

    assert quirks.index(DropEtAl()) < quirks.index(StripLastAuthorTrailing("."))


def test_profile_with__applies_the_generic_settings() -> None:
    choices = {
        "skip_issn_isbn_qualifiers": QuirkChoice(on=True, values={"preferred": ""}),
        "minus_one_unlabeled": QuirkChoice(on=False),
        "ambiguous_name_split": QuirkChoice(on=True, values={"split": "last"}),
        "csv_field_size_limit": QuirkChoice(on=True, values={"limit": "500"}),
    }

    settings = profile_with("csv", "unknown", choices).settings

    assert settings.skip_issn_isbn_qualifiers
    assert settings.preferred_issn_qualifier is None
    assert not settings.minus_one_unlabeled
    assert settings.ambiguous_name_split == "last"
    assert settings.csv_field_size_limit == 500


def test_profile_with__placeholder_values_are_semicolon_separated() -> None:
    values = {"values": "[Not Available].; n/a ;"}
    choices = {"ContinueToNextField.title": QuirkChoice(on=True, values=values)}

    [placeholder] = profile_with("nbib", "pubmed", choices).settings.continue_to_next

    assert placeholder.values == frozenset({"[Not Available].", "n/a"})
    assert placeholder.case_sensitive


def test_profile_with__placeholder_off_clears_it() -> None:
    choices = {"ContinueToNextField.title": QuirkChoice(on=False)}

    settings = profile_with("ris", "unknown", choices).settings

    assert settings.continue_to_next == ()


def test_dump_choices__round_trips() -> None:
    choices = _choices(_entries("csv", "scopus"))

    assert load_choices(dump_choices(choices)) == choices
