import csv
import logging
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from app.models.record import Author, Record

logger = logging.getLogger(__name__)

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
    authors_column: str | None = None
    keywords_column: str | None = None
    list_delimiter: str = ";"

    def __post_init__(self) -> None:
        for column, target in self.fields.items():
            if target not in SCALAR_FIELDS:
                raise ValueError(
                    f"column {column!r} maps to unknown Record field {target!r}"
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


def _apply_mapping(raw_fields: dict[str, str], mapping: ColumnMapping) -> Record:
    values: dict[str, Any] = {}
    for column, target in mapping.fields.items():
        value = raw_fields.get(column)
        if value is not None and value.strip():
            values[target] = value.strip()

    if mapping.authors_column is not None:
        names = _split_list(
            raw_fields.get(mapping.authors_column), mapping.list_delimiter
        )
        values["authors"] = [Author(full_name=name) for name in names]

    if mapping.keywords_column is not None:
        values["keywords"] = _split_list(
            raw_fields.get(mapping.keywords_column), mapping.list_delimiter
        )

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
