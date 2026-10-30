from app.models.record import Record
from app.parsers.common import ParsedRow, ParseResult, SkippedRow
from app.parsers.mapping import FieldMapping
from app.parsers.profiles import apply_profile, has_profile, profile_for
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.profiles.default import DEFAULT_PROFILES, default_settings
from app.parsers.profiles.pubmed import PUBMED
from app.parsers.quirks import FirstValue, ParseSettings, StripPrefix


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
        assert settings.skip_issn_isbn_qualifiers
        assert settings.minus_one_unlabeled
        assert settings.ambiguous_name_split == "none"
    assert DEFAULT_PROFILES["nbib"].settings.keyword_prefixes == {"MH": "[MeSH] "}


def test_default_settings__overrides_the_type_default() -> None:
    settings = default_settings("nbib", minus_one_unlabeled=False)

    assert not settings.minus_one_unlabeled
    assert settings.keyword_prefixes == {"MH": "[MeSH] "}


def test_apply_profile__runs_quirks_in_order_and_keeps_raw_fields_and_skipped() -> None:
    profile = FormatProfile(
        aliases={},
        matches=never_matches,
        settings=ParseSettings(),
        quirks=(StripPrefix("pmid", "https://x/"), FirstValue("pmid", "|")),
    )
    skipped = [SkippedRow(3, "bad")]
    raw = {"X": "https://x/1|2"}
    result = ParseResult(
        rows=[ParsedRow(Record(pmid="https://x/1|2"), raw)], skipped=skipped
    )

    fixed = apply_profile(result, profile, FieldMapping())

    assert fixed.rows[0].record.pmid == "1"
    assert fixed.rows[0].raw_fields == raw
    assert fixed.skipped == skipped
