from dataclasses import dataclass
from pathlib import Path

from app.models.record import Record

_FILE_ENCODINGS = ("utf-8-sig", "cp1252")


@dataclass
class ParsedRow:
    record: Record
    raw_fields: dict[str, str]


@dataclass
class SkippedRow:
    row_number: int
    reason: str


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    skipped: list[SkippedRow]


def decode_file(path: Path) -> str:
    raw_bytes = path.read_bytes()
    for encoding in _FILE_ENCODINGS:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path} using any of {_FILE_ENCODINGS}")
