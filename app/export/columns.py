import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.export.options import ExportOptions
from app.gui.format import DISPLAY_SEPARATOR, label_text, source_label
from app.models.record import CLEANED_DATE, Record
from app.parsers.authors import AUTHOR_JOINER, author_id_keys, author_ids_for_key
from app.parsers.mapping import split_keyword

DatePart = Literal["full", "year", "month", "day"]
ExtraKind = Literal["record_id", "sources", "source_files"]

_ORIGINAL_SUFFIX = " (original)"
_PLAIN_YEAR = re.compile(r"\d{4}")
_AUTHOR_IDS_SUFFIX = " (author IDs)"

_SCALAR_LABELS = {
    "title": "Title",
    "author_names": "Authors",
    "author_affiliations": "Affiliations",
    "journal": "Journal",
    "conference_name": "Conference",
    "volume": "Volume",
    "issue": "Issue",
    "pages": "Pages",
    "abstract": "Abstract",
    "doi": "DOI",
    "pmid": "PMID",
    "issn": "ISSN",
    "isbn": "ISBN",
    "publication_type": "Publication type",
    "language": "Language",
    "publisher": "Publisher",
    "url": "URL",
    "notes": "Notes",
}
_EXTRA_LABELS: dict[ExtraKind, str] = {
    "record_id": "Record ID",
    "sources": "Sources",
    "source_files": "Source files",
}


@dataclass(frozen=True)
class ExportSource:
    vendors: tuple[str, ...]
    filename: str
    raw_fields: dict[str, str]
    ignored_keys: frozenset[str]


@dataclass(frozen=True)
class ExportRecord:
    id: int
    record: Record
    sources: list[ExportSource] = field(default_factory=list)


@dataclass
class ExportColumn:
    """`key` identifies the column across rebuilds; `name` is the CSV header, and
    an empty name leaves the column out."""

    key: str
    label: str
    name: str


@dataclass
class ScalarColumn(ExportColumn):
    field: str


@dataclass
class JoinedColumn(ScalarColumn):
    delimiter: str = DISPLAY_SEPARATOR


@dataclass
class DateColumn(ExportColumn):
    part: DatePart = "full"


@dataclass
class KeywordsColumn(ExportColumn):
    prefix: str | None = None
    delimiter: str = DISPLAY_SEPARATOR


@dataclass
class AuthorIdKeyColumn(ExportColumn):
    id_key: str = ""
    delimiter: str = DISPLAY_SEPARATOR


@dataclass
class OtherIdColumn(ExportColumn):
    id_key: str = ""


@dataclass
class LabelColumn(ExportColumn):
    phase: str = ""
    screener: str = ""


@dataclass
class ExtraColumn(ExportColumn):
    kind: ExtraKind = "record_id"


@dataclass
class RawColumn(ExportColumn):
    raw_key: str = ""


def _scalar(field_name: str) -> ScalarColumn:
    label = _SCALAR_LABELS[field_name]
    return ScalarColumn(key=field_name, label=label, name=label, field=field_name)


def _joined(field_name: str) -> JoinedColumn:
    label = _SCALAR_LABELS[field_name]
    return JoinedColumn(key=field_name, label=label, name=label, field=field_name)


def _keywords(prefix: str | None) -> KeywordsColumn:
    label = "Keywords" if prefix is None else f"Keywords: {prefix}"
    return KeywordsColumn(
        key=f"keywords:{prefix}", label=label, name=label, prefix=prefix
    )


def _author_id_key(id_key: str, taken: set[str]) -> AuthorIdKeyColumn:
    name = id_key + _AUTHOR_IDS_SUFFIX if id_key.casefold() in taken else id_key
    return AuthorIdKeyColumn(
        key=f"author_ids:{id_key}",
        label=f"Author IDs: {id_key}",
        name=name,
        id_key=id_key,
    )


def _other_id(id_key: str) -> OtherIdColumn:
    return OtherIdColumn(
        key=f"other_id:{id_key}", label=id_key, name=id_key, id_key=id_key
    )


def _label(phase: str, screener: str) -> LabelColumn:
    label = f"Label: {phase} / {screener}"
    return LabelColumn(
        key=f"label:{phase}\x00{screener}",
        label=label,
        name=label,
        phase=phase,
        screener=screener,
    )


def _year_only(date: str) -> bool:
    match = CLEANED_DATE.fullmatch(date)
    if match is not None:
        return not (match["month"] or match["day"])
    return _PLAIN_YEAR.fullmatch(date) is not None


def _date(schemas: Sequence[Record]) -> DateColumn:
    """Suggests the year when every dated record has nothing more than a year."""
    dates = [schema.publication_date for schema in schemas if schema.publication_date]
    if dates and all(map(_year_only, dates)):
        return DateColumn(
            key="date", label="Publication date", name="Publication year", part="year"
        )
    return DateColumn(key="date", label="Publication date", name="Publication date")


def _extra(kind: ExtraKind) -> ExtraColumn:
    label = _EXTRA_LABELS[kind]
    return ExtraColumn(key=kind, label=label, name=label, kind=kind)


def _raw(raw_key: str, taken: set[str]) -> RawColumn:
    name = raw_key + _ORIGINAL_SUFFIX if raw_key.casefold() in taken else raw_key
    return RawColumn(
        key=f"raw:{raw_key}", label=f"Original: {raw_key}", name=name, raw_key=raw_key
    )


def export_columns(
    records: Sequence[ExportRecord], options: ExportOptions
) -> list[ExportColumn]:
    schemas = [export.record for export in records]
    prefixes = dict.fromkeys(
        prefix
        for schema in schemas
        for prefix, _ in map(split_keyword, schema.keywords)
        if prefix is not None
    )
    id_keys = dict.fromkeys(key for schema in schemas for key in schema.other_ids)
    id_keys_of_authors = dict.fromkeys(
        key for schema in schemas for key in author_id_keys(schema.author_ids)
    )
    label_pairs = dict.fromkeys(
        (label.phase, label.screener) for schema in schemas for label in schema.labels
    )

    columns: list[ExportColumn] = [
        _extra("record_id"),
        _scalar("title"),
        _joined("author_names"),
        _joined("author_affiliations"),
        _date(schemas),
        _scalar("journal"),
        _scalar("conference_name"),
        _scalar("volume"),
        _scalar("issue"),
        _scalar("pages"),
        _scalar("abstract"),
        _scalar("doi"),
        _scalar("pmid"),
        _joined("issn"),
        _joined("isbn"),
        *(_other_id(key) for key in id_keys),
        _scalar("publication_type"),
        _keywords(None),
        *(_keywords(prefix) for prefix in prefixes),
        _scalar("language"),
        _scalar("publisher"),
        _scalar("url"),
        _scalar("notes"),
        *(_label(phase, screener) for phase, screener in label_pairs),
        _extra("sources"),
        _extra("source_files"),
    ]

    taken = {column.name.casefold() for column in columns}
    after_authors = (
        next(i for i, c in enumerate(columns) if c.key == "author_names") + 1
    )
    columns[after_authors:after_authors] = [
        _author_id_key(key, taken) for key in id_keys_of_authors
    ]
    raw_keys = _raw_keys(records, options)
    taken = {column.name.casefold() for column in columns}
    columns.extend(_raw(key, taken) for key in raw_keys)
    if options.empty_columns:
        return columns
    return [column for column in columns if fill_count(column, records, options)]


def _raw_keys(records: Sequence[ExportRecord], options: ExportOptions) -> list[str]:
    if not (options.original_data or options.ignored_columns):
        return []
    return list(
        dict.fromkeys(
            key
            for export in records
            for source in export.sources
            for key in source.raw_fields
            if options.original_data or key in source.ignored_keys
        )
    )


def _date_text(record: Record, part: DatePart) -> str:
    """A part is only read from a cleaned YYYY/MM/DD date, or the year from a
    plain four-digit year."""
    date = record.publication_date or ""
    if part == "full":
        return date
    if part == "year" and _PLAIN_YEAR.fullmatch(date):
        return str(int(date))
    match = CLEANED_DATE.fullmatch(date)
    if match is None or not match[part]:
        return ""
    return str(int(match[part]))


def _joined_distinct(values: Sequence[str]) -> str:
    return DISPLAY_SEPARATOR.join(dict.fromkeys(value for value in values if value))


def column_value(
    column: ExportColumn, export: ExportRecord, options: ExportOptions
) -> str:
    record = export.record
    if isinstance(column, JoinedColumn):
        value = getattr(record, column.field) or ""
        return value.replace(AUTHOR_JOINER, column.delimiter)
    if isinstance(column, ScalarColumn):
        value = getattr(record, column.field)
        return "" if value is None else str(value)
    if isinstance(column, DateColumn):
        return _date_text(record, column.part)
    if isinstance(column, KeywordsColumn):
        keywords = (split_keyword(keyword) for keyword in record.keywords)
        return column.delimiter.join(
            text for prefix, text in keywords if prefix == column.prefix
        )
    if isinstance(column, AuthorIdKeyColumn):
        return author_ids_for_key(record.author_ids, column.id_key, column.delimiter)
    if isinstance(column, OtherIdColumn):
        return record.other_ids.get(column.id_key, "")
    if isinstance(column, LabelColumn):
        texts = (
            label_text(label.value, options.label_format)
            for label in record.labels
            if (label.phase, label.screener) == (column.phase, column.screener)
        )
        return DISPLAY_SEPARATOR.join(text for text in texts if text)
    if isinstance(column, ExtraColumn):
        if column.kind == "record_id":
            return str(export.id)
        if column.kind == "sources":
            return ", ".join(
                dict.fromkeys(
                    source_label(vendor)
                    for source in export.sources
                    for vendor in source.vendors or (None,)
                )
            )
        return _joined_distinct([source.filename for source in export.sources])
    if isinstance(column, RawColumn):
        return _joined_distinct(
            [source.raw_fields.get(column.raw_key, "") for source in export.sources]
        )
    raise ValueError(f"unknown export column {column!r}")


def fill_count(
    column: ExportColumn, records: Sequence[ExportRecord], options: ExportOptions
) -> int:
    return sum(bool(column_value(column, export, options)) for export in records)


def example(
    column: ExportColumn, records: Sequence[ExportRecord], options: ExportOptions
) -> str:
    values = (column_value(column, export, options) for export in records)
    return next((value for value in values if value), "")
