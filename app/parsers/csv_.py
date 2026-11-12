import csv
import logging
from collections.abc import Mapping
from functools import partial
from io import StringIO
from pathlib import Path

from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
    parse_or_skip,
)
from app.parsers.mapping import (
    FieldMapping,
    Suggest,
    apply_mapping,
    override_aliases,
)
from app.parsers.mapping import suggest_mapping as _suggest_mapping
from app.parsers.quirks import NO_QUIRKS, ParseSettings

logger = logging.getLogger(__name__)

_SCALARS = {
    "article title": "title",
    "document title": "title",
    "title": "title",
    "abstract": "abstract",
    "source title": "journal",
    "journal": "journal",
    "publication title": "journal",
    "conference name": "conference_name",
    "proceedings title": "conference_name",
    "volume": "volume",
    "issue": "issue",
    "doi": "doi",
    "pubmed id": "pmid",
    "pmid": "pmid",
    "document type": "publication_type",
    "publication type": "publication_type",
    "language of original document": "language",
    "language": "language",
    "publisher": "publisher",
    "link": "url",
    "url": "url",
    "notes": "notes",
}
_SUGGESTIONS: dict[str, Suggest] = {
    **{alias: Suggest(target) for alias, target in _SCALARS.items()},
    "pages": Suggest("pages"),
    "page range": Suggest("pages"),
    "page start": Suggest("pages", {"part": "start"}),
    "page end": Suggest("pages", {"part": "end"}),
    "issn": Suggest("issn_isbn", {"kind": "issn"}),
    "isbn": Suggest("issn_isbn", {"kind": "isbn"}),
    **dict.fromkeys(("authors", "author full names", "author(s)"), Suggest("authors")),
    **dict.fromkeys(
        ("author keywords", "index keywords", "keywords"), Suggest("keywords")
    ),
    "year": Suggest("date", {"part": "year"}),
    "publication year": Suggest("date", {"part": "year"}),
    "month": Suggest("date", {"part": "month"}),
    "day": Suggest("date", {"part": "day"}),
    **dict.fromkeys(("date", "publication date", "coverdate"), Suggest("date")),
    **dict.fromkeys(("eid", "pmcid", "pmc id"), Suggest("other_ids")),
    **dict.fromkeys(
        ("included", "label_included", "label", "decision", "inclusion"),
        Suggest("label"),
    ),
}

_EXTRA_FIELDS_KEY = "__extra__"
_SNIFF_SAMPLE_SIZE = 2048
_DELIMITERS = ",;\t"
_CONSISTENT_ROWS = 5


def _row_lengths(text: str, delimiter: str) -> set[int]:
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    try:
        rows = [row for _, row in zip(range(_CONSISTENT_ROWS), reader, strict=False)]
    except csv.Error:
        return set()
    return {len(row) for row in rows if row} if len(rows) > 1 else set()


def _consistent_delimiter(text: str) -> str | None:
    """The delimiter giving the first rows one same column count above one; the
    most columns wins."""
    best, best_columns = None, 1
    for delimiter in _DELIMITERS:
        lengths = _row_lengths(text, delimiter)
        if len(lengths) == 1 and (columns := lengths.pop()) > best_columns:
            best, best_columns = delimiter, columns
    return best


def sniff_dialect(text: str) -> type[csv.Dialect] | None:
    """The sniffer gives up when its sample cuts through long quoted cells; the
    reader then tries each delimiter on the first rows."""
    try:
        dialect = csv.Sniffer().sniff(text[:_SNIFF_SAMPLE_SIZE], delimiters=_DELIMITERS)
    except csv.Error:
        delimiter = _consistent_delimiter(text)
        if delimiter is None:
            return None
        return type("ConsistentDialect", (csv.excel,), {"delimiter": delimiter})
    # The sniffer guesses doublequote=False when its sample has no "" escape.
    dialect.doublequote = True
    return dialect


def _dialect(text: str, delimiter: str | None) -> type[csv.Dialect] | csv.Dialect | str:
    if delimiter is None:
        return sniff_dialect(text) or "excel"
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

        parse_or_skip(
            rows,
            skipped,
            row_number,
            partial(parse_csv_record, raw_fields, mapping, settings),
        )

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
    overrides: Mapping[str, Suggest] | None = None,
    ignored_keys: frozenset[str] = frozenset(),
) -> FieldMapping:
    suggestions = override_aliases(_SUGGESTIONS, overrides or {})
    kept = [h for h in headers if h.strip().lower() not in ignored_keys]
    return _suggest_mapping(kept, suggestions, lenient=True)
