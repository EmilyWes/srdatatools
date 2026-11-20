import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from app.gui.export.options import ExportOptions
from app.gui.export.ris_tags import TAG_PATTERN, ris_type
from app.helpers.format import DISPLAY_SEPARATOR, label_text, source_label
from app.models.record import CLEANED_DATE, Record
from app.parsers.authors import (
    AUTHOR_JOINER,
    author_id_keys,
    author_ids_for_key,
    author_ids_per_slot,
)
from app.parsers.mapping import split_keyword

DatePart = Literal["full", "year", "month", "day", "ris"]
PagesPart = Literal["start", "end"]
ExtraKind = Literal["record_id", "sources", "source_files"]

_ORIGINAL_SUFFIX = " (original)"
_PLAIN_YEAR = re.compile(r"\d{4}")
_AUTHOR_IDS_SUFFIX = " (author IDs)"
_PAGE_DASH = "-"

_RIS_TAGS = {
    "record_id": "ID",
    "title": "TI",
    "author_names": "AU",
    "author_affiliations": "AD",
    "journal": "T2",
    "conference_name": "T2",
    "volume": "VL",
    "issue": "IS",
    "pages": "SP",
    "abstract": "AB",
    "doi": "DO",
    "pmid": "AN",
    "issn": "SN",
    "isbn": "SN",
    "language": "LA",
    "publisher": "PB",
    "url": "UR",
    "notes": "N1",
}
NOTE_TAG = "N1"
_KEYWORD_TAG = "KW"
_UNCHECKED_IN_RIS = frozenset({"sources", "source_files"})

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
    """`key` identifies the column across rebuilds; `name` is the CSV header or
    RIS tag. A RIS N1 line starts with `note_name`."""

    key: str
    label: str
    name: str
    note_name: str = field(default="", kw_only=True)
    default_checked: bool = field(default=True, kw_only=True)


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
class PagesColumn(ExportColumn):
    part: PagesPart = "start"


@dataclass
class RisTypeColumn(ExportColumn):
    pass


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
    if options.file_type == "ris":
        columns = _ris_columns(columns, options)
    if options.empty_columns:
        return columns
    return [column for column in columns if fill_count(column, records, options)]


def default_note_name(column: ExportColumn) -> str:
    return column.raw_key if isinstance(column, RawColumn) else column.label


def _ris_column(column: ExportColumn) -> ExportColumn:
    """A row without a tag of its own goes to N1, its line starting with its name."""
    if isinstance(column, KeywordsColumn):
        return replace(column, name=_KEYWORD_TAG)
    if column.key in _RIS_TAGS:
        return replace(column, name=_RIS_TAGS[column.key])
    note_name = default_note_name(column)
    if isinstance(column, RawColumn):
        if TAG_PATTERN.fullmatch(column.raw_key):
            return replace(column, name=column.raw_key)
        return replace(column, name=NOTE_TAG, note_name=note_name)
    checked = not (
        isinstance(column, AuthorIdKeyColumn) or column.key in _UNCHECKED_IN_RIS
    )
    return replace(column, name=NOTE_TAG, note_name=note_name, default_checked=checked)


def _ris_columns(
    columns: Sequence[ExportColumn], options: ExportOptions
) -> list[ExportColumn]:
    """TY comes first; the date becomes a PY and a DA row, and pages an SP and an
    EP row when split."""
    result: list[ExportColumn] = [
        RisTypeColumn(key="publication_type", label="Publication type", name="TY")
    ]
    for column in columns:
        if column.key == "publication_type":
            continue
        if isinstance(column, DateColumn):
            result += [
                DateColumn(
                    key="date:year", label="Publication year", name="PY", part="year"
                ),
                DateColumn(key="date", label="Publication date", name="DA", part="ris"),
            ]
        elif column.key == "pages" and options.split_pages:
            result += [
                PagesColumn(key="pages:start", label="Start page", name="SP"),
                PagesColumn(key="pages:end", label="End page", name="EP", part="end"),
            ]
        else:
            result.append(_ris_column(column))
    return result


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


def _date_text(record: Record, part: DatePart, options: ExportOptions) -> str:
    """A part is only read from a cleaned YYYY/MM/DD date, or the year from a
    plain four-digit year. RIS writes a cleaned date as YYYY/MM/DD/."""
    date = record.publication_date or ""
    if part == "full":
        return date
    if part == "ris":
        cleaned = CLEANED_DATE.fullmatch(date)
        if cleaned is None:
            return "" if options.cleaned_dates_only else date
        return f"{cleaned['year']}/{cleaned['month'] or ''}/{cleaned['day'] or ''}/"
    if part == "year" and _PLAIN_YEAR.fullmatch(date):
        return str(int(date))
    match = CLEANED_DATE.fullmatch(date)
    if match is None or not match[part]:
        return ""
    return str(int(match[part]))


def _joined_distinct(values: Sequence[str]) -> str:
    return DISPLAY_SEPARATOR.join(dict.fromkeys(value for value in values if value))


def _keyword_texts(column: KeywordsColumn, record: Record) -> list[str]:
    keywords = (split_keyword(keyword) for keyword in record.keywords)
    return [text for prefix, text in keywords if prefix == column.prefix]


def _label_texts(
    column: LabelColumn, record: Record, options: ExportOptions
) -> list[str]:
    texts = (
        label_text(label.value, options.label_format)
        for label in record.labels
        if (label.phase, label.screener) == (column.phase, column.screener)
    )
    return [text for text in texts if text]


def column_values(
    column: ExportColumn, export: ExportRecord, options: ExportOptions
) -> list[str]:
    """The separate non-empty values, for one RIS line each."""
    record = export.record
    values: list[str]
    if isinstance(column, JoinedColumn):
        values = (getattr(record, column.field) or "").split(AUTHOR_JOINER)
    elif isinstance(column, KeywordsColumn):
        values = _keyword_texts(column, record)
    elif isinstance(column, AuthorIdKeyColumn):
        values = author_ids_per_slot(record.author_ids, column.id_key)
    elif isinstance(column, LabelColumn):
        values = _label_texts(column, record, options)
    elif isinstance(column, ScalarColumn) and column.field == "notes":
        # Repeated RIS N1 lines are stored as one value, a line each.
        values = (record.notes or "").splitlines()
    else:
        values = [column_value(column, export, options)]
    return [value for value in values if value]


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
        return _date_text(record, column.part, options)
    if isinstance(column, PagesColumn):
        start, _, end = (record.pages or "").partition(_PAGE_DASH)
        return (start if column.part == "start" else end).strip()
    if isinstance(column, RisTypeColumn):
        return ris_type(record.publication_type)
    if isinstance(column, KeywordsColumn):
        return column.delimiter.join(_keyword_texts(column, record))
    if isinstance(column, AuthorIdKeyColumn):
        return author_ids_for_key(record.author_ids, column.id_key, column.delimiter)
    if isinstance(column, OtherIdColumn):
        return record.other_ids.get(column.id_key, "")
    if isinstance(column, LabelColumn):
        return DISPLAY_SEPARATOR.join(_label_texts(column, record, options))
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
