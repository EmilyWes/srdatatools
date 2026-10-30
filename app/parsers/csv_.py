import csv
import logging
from io import StringIO
from pathlib import Path

from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
)
from app.parsers.mapping import FieldMapping, apply_mapping, override_aliases
from app.parsers.mapping import suggest_mapping as _suggest_mapping
from app.parsers.quirks import NO_QUIRKS, ParseSettings

logger = logging.getLogger(__name__)

_SUGGESTION_ALIASES: dict[str, list[str]] = {
    "title": ["article title", "document title", "title"],
    "abstract": ["abstract"],
    "journal": ["source title", "journal", "publication title"],
    "conference_name": ["conference name", "proceedings title"],
    "volume": ["volume"],
    "issue": ["issue"],
    "pages": ["pages", "page range"],
    "page_start": ["page start"],
    "page_end": ["page end"],
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
    "other_ids": ["eid", "pmcid", "pmc id"],
    "label": ["included", "label_included", "label", "decision", "inclusion"],
}

_EXTRA_FIELDS_KEY = "__extra__"


def _sniff_dialect(sample: str) -> type[csv.Dialect] | str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return "excel"
    # The sniffer guesses doublequote=False when its sample has no "" escape.
    dialect.doublequote = True
    return dialect


def _dialect(text: str, delimiter: str | None) -> type[csv.Dialect] | csv.Dialect | str:
    if delimiter is None:
        return _sniff_dialect(text[:2048])
    dialect = csv.excel()
    dialect.delimiter = delimiter
    return dialect


def parse_csv_record(
    raw_fields: dict[str, str],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> ParsedRow:
    record = apply_mapping(raw_fields, mapping, settings)
    return ParsedRow(record=record, raw_fields=raw_fields)


def parse_csv_text(
    text: str,
    mapping: FieldMapping,
    delimiter: str | None = None,
    settings: ParseSettings = NO_QUIRKS,
) -> ParseResult:
    csv.field_size_limit(settings.csv_field_size_limit)
    dialect = _dialect(text, delimiter)
    reader = csv.DictReader(
        StringIO(text), dialect=dialect, restkey=_EXTRA_FIELDS_KEY, restval=None
    )
    fieldnames = reader.fieldnames or []

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    row_number = 1
    while True:
        row_number += 1
        try:
            raw_row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            skipped.append(SkippedRow(row_number, str(exc)))
            logger.warning("Skipping row %d: %s", row_number, exc)
            continue
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

        rows.append(parse_csv_record(raw_fields, mapping, settings))

    return ParseResult(rows=rows, skipped=skipped)


def parse_csv_file(
    path: Path,
    mapping: FieldMapping,
    delimiter: str | None = None,
    settings: ParseSettings = NO_QUIRKS,
) -> ParseResult:
    return parse_csv_text(decode_file(path), mapping, delimiter, settings)


def read_csv_headers(
    path: Path, delimiter: str | None = None, settings: ParseSettings = NO_QUIRKS
) -> FileSummary:
    csv.field_size_limit(settings.csv_field_size_limit)
    text = decode_file(path)
    dialect = _dialect(text, delimiter)
    reader = csv.reader(StringIO(text), dialect=dialect)
    headers = next(reader, [])
    summary = SummaryBuilder(headers)
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            logger.warning("Skipping row at line %d: %s", reader.line_num, exc)
            continue
        if not row:
            continue
        for header, value in zip(headers, row, strict=False):
            summary.add(header, value)
        summary.end_record()
    return summary.build()


def suggest_mapping(
    headers: list[str],
    alias_overrides: dict[str, list[str]] | None = None,
    ignored_keys: frozenset[str] = frozenset(),
) -> FieldMapping:
    aliases = override_aliases(_SUGGESTION_ALIASES, alias_overrides or {})
    kept = [h for h in headers if h.strip().lower() not in ignored_keys]
    return _suggest_mapping(kept, aliases, lenient=True)
