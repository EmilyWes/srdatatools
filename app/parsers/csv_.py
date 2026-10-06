import csv
import logging
from io import StringIO
from pathlib import Path

from app.parsers.common import ParsedRow, ParseResult, SkippedRow, decode_file
from app.parsers.mapping import FieldMapping, apply_mapping
from app.parsers.mapping import suggest_mapping as _suggest_mapping

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
}

_EXTRA_FIELDS_KEY = "__extra__"


def _sniff_dialect(sample: str) -> type[csv.Dialect] | str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return "excel"


def parse_csv_text(text: str, mapping: FieldMapping) -> ParseResult:
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

        record = apply_mapping(raw_fields, mapping)
        rows.append(ParsedRow(record=record, raw_fields=raw_fields))

    return ParseResult(rows=rows, skipped=skipped)


def parse_csv_file(path: Path, mapping: FieldMapping) -> ParseResult:
    return parse_csv_text(decode_file(path), mapping)


def read_csv_headers(path: Path) -> dict[str, str]:
    text = decode_file(path)
    dialect = _sniff_dialect(text[:2048])
    reader = csv.reader(StringIO(text), dialect=dialect)
    headers = next(reader, [])
    samples = dict.fromkeys(headers, "")
    for row in reader:
        for header, value in zip(headers, row, strict=False):
            if not samples[header]:
                samples[header] = value.strip()
        if all(samples.values()):
            break
    return samples


def suggest_mapping(headers: list[str]) -> FieldMapping:
    return _suggest_mapping(headers, _SUGGESTION_ALIASES, lenient=True)
