from collections.abc import Callable
from dataclasses import dataclass, replace

from app.models.record import Record
from app.parsers.common import ParseResult
from app.parsers.mapping import FieldMapping, RowDefaults, Suggest
from app.parsers.quirks import ParseSettings, RecordQuirk

MatchesText = Callable[[str], bool]


@dataclass(frozen=True)
class FormatProfile:
    suggestions: dict[str, Suggest]
    matches: MatchesText
    settings: ParseSettings
    row_defaults: RowDefaults
    quirks: tuple[RecordQuirk, ...] = ()
    ignored_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    formats: dict[str, FormatProfile]


def never_matches(text: str) -> bool:
    return False


def fix_record(
    profile: FormatProfile,
    raw_fields: dict[str, str],
    record: Record,
    mapping: FieldMapping,
) -> Record:
    for quirk in profile.quirks:
        record = quirk.apply(raw_fields, record, mapping, profile.settings)
    return record


def apply_profile(
    result: ParseResult, profile: FormatProfile, mapping: FieldMapping
) -> ParseResult:
    rows = [
        replace(row, record=fix_record(profile, row.raw_fields, row.record, mapping))
        for row in result.rows
    ]
    return replace(result, rows=rows)
