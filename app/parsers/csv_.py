import csv
import difflib
import logging
import re
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.record import Author, PartialDate, Record

logger = logging.getLogger(__name__)

_FILE_ENCODINGS = ("utf-8-sig", "cp1252")

_SUGGESTION_ALIASES: dict[str, list[str]] = {
    "title": ["article title", "document title", "title"],
    "abstract": ["abstract"],
    "journal": ["source title", "journal", "publication title"],
    "conference_name": ["conference name", "proceedings title"],
    "volume": ["volume"],
    "issue": ["issue"],
    "pages": ["pages", "page range"],
    "doi": ["doi"],
    "pmid": ["pubmed id", "pmid"],
    "issn": ["issn"],
    "isbn": ["isbn"],
    "publication_type": ["document type", "publication type"],
    "language": ["language of original document", "language"],
    "publisher": ["publisher"],
    "url": ["link", "url"],
    "notes": ["notes"],
    "authors": ["authors", "author full names", "author(s)"],
    "keywords": ["author keywords", "index keywords", "keywords"],
    "year": ["year", "publication year"],
    "month": ["month"],
    "day": ["day"],
    "date": ["date", "publication date", "coverdate"],
    "other_ids": ["eid"],
}

_SUGGESTION_CUTOFF = 0.6

_MONTH_ABBREVIATIONS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_DATE_PATTERNS = [
    re.compile(r"^(?P<year>\d{4})$"),
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})$"),
]

SCALAR_FIELDS = frozenset(
    {
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
)

_EXTRA_FIELDS_KEY = "__extra__"


@dataclass
class ColumnMapping:
    fields: dict[str, str] = field(default_factory=dict)
    authors_columns: list[str] = field(default_factory=list)
    keywords_columns: list[str] = field(default_factory=list)
    list_delimiter: str = ";"
    date_column: str | None = None
    year_column: str | None = None
    month_column: str | None = None
    day_column: str | None = None

    def __post_init__(self) -> None:
        for column, target in self.fields.items():
            if target in SCALAR_FIELDS:
                continue
            if target.startswith("other_ids.") and len(target) > len("other_ids."):
                continue
            raise ValueError(
                f"column {column!r} maps to unknown Record field {target!r}"
            )
        if self.date_column is not None and (
            self.year_column is not None
            or self.month_column is not None
            or self.day_column is not None
        ):
            raise ValueError(
                "date_column cannot be combined with "
                "year_column/month_column/day_column"
            )


@dataclass
class ParsedRow:
    record: Record
    raw_fields: dict[str, str]


@dataclass
class SkippedRow:
    row_number: int
    reason: str


@dataclass
class CsvParseResult:
    rows: list[ParsedRow]
    skipped: list[SkippedRow]


def _sniff_dialect(sample: str) -> type[csv.Dialect] | str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return "excel"


def _split_list(value: str | None, delimiter: str) -> list[str]:
    if value is None:
        return []
    return [piece.strip() for piece in value.split(delimiter) if piece.strip()]


def _parse_int_field(value: str | None, field_name: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        logger.warning("Could not parse %s value %r", field_name, value)
        return None


def _parse_month(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    abbreviation = stripped[:3].lower()
    if abbreviation in _MONTH_ABBREVIATIONS:
        return _MONTH_ABBREVIATIONS[abbreviation]
    logger.warning("Could not parse month value %r", value)
    return None


def _build_partial_date(
    year: int | None, month: int | None, day: int | None
) -> PartialDate | None:
    if year is None and month is None and day is None:
        return None
    try:
        return PartialDate(year=year, month=month, day=day)
    except ValidationError:
        logger.warning("Dropping day %r because month is missing", day)
        return PartialDate(year=year, month=month, day=None)


def _parse_date_string(value: str) -> PartialDate | None:
    stripped = value.strip()
    for pattern in _DATE_PATTERNS:
        match = pattern.match(stripped)
        if match is None:
            continue
        parts = match.groupdict()
        return _build_partial_date(
            year=int(parts["year"]),
            month=int(parts["month"]) if parts.get("month") else None,
            day=int(parts["day"]) if parts.get("day") else None,
        )
    logger.warning("Could not parse date value %r", value)
    return None


def _parse_publication_date(
    raw_fields: dict[str, str], mapping: ColumnMapping
) -> PartialDate | None:
    if mapping.date_column is not None:
        raw_date = raw_fields.get(mapping.date_column)
        if raw_date is not None and raw_date.strip():
            return _parse_date_string(raw_date)
        return None

    if (
        mapping.year_column is None
        and mapping.month_column is None
        and mapping.day_column is None
    ):
        return None

    year = (
        _parse_int_field(raw_fields.get(mapping.year_column), "year")
        if mapping.year_column is not None
        else None
    )
    month = (
        _parse_month(raw_fields.get(mapping.month_column))
        if mapping.month_column is not None
        else None
    )
    day = (
        _parse_int_field(raw_fields.get(mapping.day_column), "day")
        if mapping.day_column is not None
        else None
    )
    return _build_partial_date(year, month, day)


def _apply_mapping(raw_fields: dict[str, str], mapping: ColumnMapping) -> Record:
    values: dict[str, Any] = {}
    other_ids: dict[str, str] = {}
    for column, target in mapping.fields.items():
        value = raw_fields.get(column)
        if value is None or not value.strip():
            continue
        if target.startswith("other_ids."):
            other_ids[target.removeprefix("other_ids.")] = value.strip()
        else:
            values[target] = value.strip()
    if other_ids:
        values["other_ids"] = other_ids

    if mapping.authors_columns:
        names: list[str] = []
        for column in mapping.authors_columns:
            names.extend(_split_list(raw_fields.get(column), mapping.list_delimiter))
        values["authors"] = [Author(full_name=name) for name in names]

    if mapping.keywords_columns:
        keywords: list[str] = []
        for column in mapping.keywords_columns:
            keywords.extend(_split_list(raw_fields.get(column), mapping.list_delimiter))
        values["keywords"] = keywords

    publication_date = _parse_publication_date(raw_fields, mapping)
    if publication_date is not None:
        values["publication_date"] = publication_date

    return Record(**values)


def parse_csv_text(text: str, mapping: ColumnMapping) -> CsvParseResult:
    dialect = _sniff_dialect(text[:2048])
    reader = csv.DictReader(
        StringIO(text), dialect=dialect, restkey=_EXTRA_FIELDS_KEY, restval=None
    )
    fieldnames = reader.fieldnames or []

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for row_number, raw_row in enumerate(reader, start=2):
        if _EXTRA_FIELDS_KEY in raw_row:
            reason = f"row has more fields than the {len(fieldnames)}-column header"
            skipped.append(SkippedRow(row_number, reason))
            logger.warning("Skipping row %d: %s", row_number, reason)
            continue
        if any(value is None for value in raw_row.values()):
            reason = f"row has fewer fields than the {len(fieldnames)}-column header"
            skipped.append(SkippedRow(row_number, reason))
            logger.warning("Skipping row %d: %s", row_number, reason)
            continue

        raw_fields: dict[str, str] = dict(raw_row)
        if all(not value.strip() for value in raw_fields.values()):
            skipped.append(SkippedRow(row_number, "row is blank"))
            logger.warning("Skipping row %d: blank", row_number)
            continue

        record = _apply_mapping(raw_fields, mapping)
        rows.append(ParsedRow(record=record, raw_fields=raw_fields))

    return CsvParseResult(rows=rows, skipped=skipped)


def _decode_file(path: Path) -> str:
    raw_bytes = path.read_bytes()
    for encoding in _FILE_ENCODINGS:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path} using any of {_FILE_ENCODINGS}")


def parse_csv_file(path: Path, mapping: ColumnMapping) -> CsvParseResult:
    return parse_csv_text(_decode_file(path), mapping)


def read_csv_headers(path: Path) -> list[str]:
    text = _decode_file(path)
    dialect = _sniff_dialect(text[:2048])
    reader = csv.reader(StringIO(text), dialect=dialect)
    return next(reader, [])


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    alias_to_target = {
        alias: target
        for target, aliases in _SUGGESTION_ALIASES.items()
        for alias in aliases
    }

    suggestions: dict[str, str | None] = {}
    for header in headers:
        normalized = header.strip().lower()
        target = alias_to_target.get(normalized)
        if target is None:
            matches = difflib.get_close_matches(
                normalized, alias_to_target.keys(), n=1, cutoff=_SUGGESTION_CUTOFF
            )
            target = alias_to_target[matches[0]] if matches else None
        suggestions[header] = target

    return suggestions
