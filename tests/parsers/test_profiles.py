from app.models.record import Record
from app.parsers.common import ParsedRow, ParseResult, SkippedRow
from app.parsers.profiles import apply_profile, profile_for
from app.parsers.profiles.base import FormatProfile
from app.parsers.profiles.pubmed import PUBMED


def test_profile_for__returns_format_profile_of_known_source() -> None:
    assert profile_for("pubmed", "nbib") is PUBMED.formats["nbib"]


def test_profile_for__source_without_that_format_returns_none() -> None:
    assert profile_for("pubmed", "ris") is None


def test_profile_for__unknown_source_returns_none() -> None:
    assert profile_for("unknown", "nbib") is None


def test_apply_profile__without_profile_returns_result_unchanged() -> None:
    result = ParseResult(rows=[ParsedRow(Record(title="A"), {"TI": "A"})], skipped=[])

    assert apply_profile(result, None) is result


def test_apply_profile__fixes_records_and_keeps_raw_fields_and_skipped() -> None:
    profile = FormatProfile(
        aliases={},
        fix_record=lambda raw, record: record.model_copy(update={"title": raw["X"]}),
    )
    skipped = [SkippedRow(3, "bad")]
    result = ParseResult(
        rows=[ParsedRow(Record(title="A"), {"X": "fixed"})], skipped=skipped
    )

    fixed = apply_profile(result, profile)

    assert fixed.rows[0].record.title == "fixed"
    assert fixed.rows[0].raw_fields == {"X": "fixed"}
    assert fixed.skipped == skipped
