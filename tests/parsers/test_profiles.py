from app.models.record import Author, Record
from app.parsers.common import ParsedRow, ParseResult, SkippedRow
from app.parsers.mapping import FieldMapping, RowDefaults
from app.parsers.profiles import apply_profile, has_profile, profile_for
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.profiles.default import (
    DEFAULT_PROFILES,
    default_quirks,
    default_row_defaults,
    default_settings,
)
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.profiles.scopus import SCOPUS
from app.parsers.quirks import (
    DropEtAl,
    EmbeddedAuthorIds,
    ExpandPageRange,
    FirstValue,
    ParseSettings,
    StripDoi,
    StripLastAuthorTrailing,
    StripPmid,
)


def test_profile_for__returns_format_profile_of_known_source() -> None:
    assert profile_for("pubmed", "nbib") is PUBMED.formats["nbib"]


def test_profile_for__source_without_that_format_returns_type_default() -> None:
    assert profile_for("pubmed", "ris") is DEFAULT_PROFILES["ris"]


def test_profile_for__unknown_source_returns_type_default() -> None:
    assert profile_for("unknown", "nbib") is DEFAULT_PROFILES["nbib"]


def test_profile_for__unsupported_type_returns_none() -> None:
    assert profile_for("unknown", "unknown") is None


def test_has_profile__only_for_a_source_that_exports_the_type() -> None:
    assert has_profile("pubmed", "nbib")
    assert not has_profile("pubmed", "ris")
    assert not has_profile("unknown", "nbib")


def test_default_profiles__turn_on_the_generic_quirks() -> None:
    for settings in (profile.settings for profile in DEFAULT_PROFILES.values()):
        assert settings.issn_isbn_strip_extras
        assert settings.issn_isbn_only_one
        assert settings.label_values == ()
        assert settings.ambiguous_name_split == "none"


def test_default_profiles__turn_on_the_generic_quirks_for_every_type() -> None:
    for profile in DEFAULT_PROFILES.values():
        assert DropEtAl() in profile.quirks
        assert StripDoi() in profile.quirks
        assert StripPmid() in profile.quirks
        assert ExpandPageRange() in profile.quirks
        assert profile.settings.empty_values == ("[Not Available].",)


def test_default_profiles__nbib_keeps_first_publication_type() -> None:
    assert FirstValue("publication_type", "\n") in DEFAULT_PROFILES["nbib"].quirks
    assert FirstValue("publication_type", "\n") not in DEFAULT_PROFILES["ris"].quirks


def test_default_quirks__profile_quirks_come_after_the_type_defaults() -> None:
    own = FirstValue("doi", "x")

    assert default_quirks("ris", own) == (*DEFAULT_PROFILES["ris"].quirks, own)


def test_profiles__build_on_their_type_defaults() -> None:
    pubmed_csv = PUBMED.formats["csv"].quirks
    scopus_csv = SCOPUS.formats["csv"].quirks

    assert pubmed_csv[: len(DEFAULT_PROFILES["csv"].quirks)] == (
        DEFAULT_PROFILES["csv"].quirks
    )
    assert StripLastAuthorTrailing() in pubmed_csv
    assert StripLastAuthorTrailing() not in scopus_csv
    assert EmbeddedAuthorIds("scopus_author_id") not in DEFAULT_PROFILES["csv"].quirks


def test_default_settings__overrides_the_type_default() -> None:
    settings = default_settings("nbib", label_values=(("-1", "exclude"),))

    assert settings.label_values == (("-1", "exclude"),)
    assert settings.issn_isbn_strip_extras


def test_default_profiles__use_each_types_row_defaults() -> None:
    assert DEFAULT_PROFILES["csv"].row_defaults == RowDefaults()
    assert DEFAULT_PROFILES["ris"].row_defaults == RowDefaults(delimiter="\n")
    assert DEFAULT_PROFILES["nbib"].row_defaults == RowDefaults(delimiter="\n")
    assert DEFAULT_PROFILES["bibtex"].row_defaults == RowDefaults(author_delimiter="\n")


def test_default_row_defaults__overrides_the_type_default() -> None:
    defaults = default_row_defaults("bibtex", delimiter=",")

    assert defaults == RowDefaults(delimiter=",", author_delimiter="\n")


class _FailOnBadTitle:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: FieldMapping,
        settings: ParseSettings,
    ) -> Record:
        if record.title == "Bad":
            raise ValueError("bad value")
        return record


def test_apply_profile__skips_record_a_quirk_fails_on_in_row_order() -> None:
    profile = FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=ParseSettings(),
        row_defaults=RowDefaults(),
        quirks=(_FailOnBadTitle(),),
    )
    rows = [
        ParsedRow(Record(title=title), {}, row_number)
        for title, row_number in (("Good", 2), ("Bad", 3), ("Also", 5))
    ]
    result = ParseResult(rows=rows, skipped=[SkippedRow(4, "blank")])

    fixed = apply_profile(result, profile, FieldMapping())

    assert [row.record.title for row in fixed.rows] == ["Good", "Also"]
    assert fixed.skipped == [SkippedRow(3, "bad value"), SkippedRow(4, "blank")]


def test_apply_profile__runs_quirks_in_order_and_keeps_raw_fields_and_skipped() -> None:
    profile = FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=ParseSettings(),
        row_defaults=RowDefaults(),
        quirks=(DropEtAl(), StripLastAuthorTrailing()),
    )
    skipped = [SkippedRow(3, "bad")]
    raw = {"X": "Smith J.; et al."}
    authors = [Author(full_name="Smith J."), Author(full_name="et al.")]
    result = ParseResult(
        rows=[ParsedRow(Record(authors=authors), raw)], skipped=skipped
    )

    fixed = apply_profile(result, profile, FieldMapping())

    assert fixed.rows[0].record.authors == [Author(full_name="Smith J")]
    assert fixed.rows[0].raw_fields == raw
    assert fixed.skipped == skipped
