from collections.abc import Callable
from dataclasses import dataclass, replace

from app.models.record import Record
from app.parsers.common import ParseResult

FixRecord = Callable[[dict[str, str], Record], Record]


@dataclass(frozen=True)
class FormatProfile:
    aliases: dict[str, list[str]]
    fix_record: FixRecord
    list_delimiter: str | None = None


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    formats: dict[str, FormatProfile]


def apply_profile(result: ParseResult, profile: FormatProfile | None) -> ParseResult:
    if profile is None:
        return result
    rows = [
        replace(row, record=profile.fix_record(row.raw_fields, row.record))
        for row in result.rows
    ]
    return replace(result, rows=rows)
