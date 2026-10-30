from collections.abc import Callable
from dataclasses import dataclass, replace

from app.models.record import Record
from app.parsers.common import ParseResult
from app.parsers.mapping import FieldMapping

# Gets the mapping so a fix never reads a column the user set to ignore.
FixRecord = Callable[[dict[str, str], Record, FieldMapping], Record]
MatchesText = Callable[[str], bool]


@dataclass(frozen=True)
class FormatProfile:
    aliases: dict[str, list[str]]
    fix_record: FixRecord
    matches: MatchesText
    list_delimiter: str | None = None
    ignored_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    formats: dict[str, FormatProfile]


def apply_profile(
    result: ParseResult, profile: FormatProfile | None, mapping: FieldMapping
) -> ParseResult:
    if profile is None:
        return result
    rows = [
        replace(row, record=profile.fix_record(row.raw_fields, row.record, mapping))
        for row in result.rows
    ]
    return replace(result, rows=rows)
