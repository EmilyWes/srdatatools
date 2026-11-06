import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.models.record import Record
from app.parsers.common import ParsedRow, ParseResult, SkippedRow
from app.parsers.mapping import FieldMapping, RowDefaults, Suggest
from app.parsers.quirks import ParseSettings, RecordQuirk

logger = logging.getLogger(__name__)

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
    """A record a quirk fails on is skipped, like one the parser fails on."""
    rows: list[ParsedRow] = []
    skipped = list(result.skipped)
    for row in result.rows:
        try:
            record = fix_record(profile, row.raw_fields, row.record, mapping)
        except ValueError as exc:
            logger.warning("Skipping record at %d", row.row_number, exc_info=True)
            skipped.append(SkippedRow(row.row_number, str(exc)))
            continue
        rows.append(replace(row, record=record))
    skipped.sort(key=lambda row: row.row_number)
    return ParseResult(rows=rows, skipped=skipped)
