from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import JSON, ColumnElement, String, and_, case, cast, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.db.models import ActivityLog, Label, Record, RecordSource, SourceFile
from app.export.columns import ExportRecord, ExportSource
from app.models.record import Label as LabelSchema
from app.models.record import Record as RecordSchema
from app.models.record import publication_year
from app.parsers.mapping import split_keyword

_EMPTY_JSON = ("[]", "{}", "null")


def list_source_files(session: Session) -> list[SourceFile]:
    statement = select(SourceFile).order_by(SourceFile.imported_at)
    return list(session.scalars(statement))


def list_activity_log(session: Session) -> list[ActivityLog]:
    statement = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
    return list(session.scalars(statement))


def list_record_rows(session: Session, fields: Sequence[str]) -> list[dict[str, Any]]:
    statement = select(
        Record.id, *(getattr(Record, field) for field in fields)
    ).order_by(Record.id)
    return [dict(row) for row in session.execute(statement).mappings()]


def list_record_sources(session: Session) -> dict[int, list[str | None]]:
    statement = (
        select(RecordSource.record_id, SourceFile.source)
        .join(RecordSource.source_file)
        .order_by(RecordSource.id)
    )
    sources: dict[int, list[str | None]] = defaultdict(list)
    for record_id, source in session.execute(statement):
        sources[record_id].append(source)
    return sources


def list_label_columns(session: Session) -> list[tuple[str, str]]:
    statement = (
        select(Label.phase, Label.screener)
        .group_by(Label.phase, Label.screener)
        .order_by(func.min(Label.id))
    )
    return [(phase, screener) for phase, screener in session.execute(statement)]


def list_record_labels(
    session: Session,
) -> dict[int, dict[tuple[str, str], list[str]]]:
    statement = select(
        Label.record_id, Label.phase, Label.screener, Label.value
    ).order_by(Label.id)
    labels: dict[int, dict[tuple[str, str], list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record_id, phase, screener, value in session.execute(statement):
        labels[record_id][(phase, screener)].append(value)
    return {record_id: dict(pairs) for record_id, pairs in labels.items()}


def count_records(session: Session) -> int:
    return session.scalar(select(func.count(Record.id))) or 0


def count_records_for_file(session: Session, source_file_id: int) -> int:
    statement = select(func.count(func.distinct(RecordSource.record_id))).where(
        RecordSource.source_file_id == source_file_id
    )
    return session.scalar(statement) or 0


def count_records_per_year(session: Session) -> list[tuple[int | None, int]]:
    counts = Counter(
        publication_year(date)
        for date in session.scalars(select(Record.publication_date))
    )
    return sorted(counts.items(), key=lambda item: (item[0] is None, item[0] or 0))


def count_label_values(session: Session) -> dict[tuple[str, str], dict[str, int]]:
    total = count_records(session)
    labels = list_record_labels(session).values()
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for pair in list_label_columns(session):
        values = Counter(value for pairs in labels for value in pairs.get(pair, []))
        missing = total - sum(pair in pairs for pairs in labels)
        if missing:
            values["unlabeled"] += missing
        counts[pair] = dict(values)
    return counts


def _is_filled(column: InstrumentedAttribute[Any]) -> ColumnElement[bool]:
    """JSON columns are compared as stored text, so no row has to be loaded."""
    if isinstance(column.type, JSON):
        return cast(column, String).not_in(_EMPTY_JSON)
    return and_(column.is_not(None), column != "")


def count_filled_fields(
    session: Session, fields: Sequence[str]
) -> list[tuple[str, int]]:
    columns = [getattr(Record, field) for field in fields]
    statement = select(*(func.count(case((_is_filled(c), 1))) for c in columns))
    return list(zip(fields, session.execute(statement).one(), strict=True))


def count_keywords(session: Session) -> dict[str | None, list[tuple[str, int]]]:
    """Grouped case-insensitively; the first spelling seen is shown."""
    spellings: dict[tuple[str | None, str], str] = {}
    counts: dict[str | None, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for keywords in session.scalars(select(Record.keywords).order_by(Record.id)):
        seen = set()
        for keyword in keywords:
            prefix, text = split_keyword(keyword)
            key = (prefix, text.casefold())
            if key in seen:
                continue
            seen.add(key)
            spelling = spellings.setdefault(key, text)
            counts[prefix][spelling] += 1
    return {
        prefix: sorted(texts.items(), key=lambda item: (-item[1], item[0].casefold()))
        for prefix, texts in counts.items()
    }


def list_keyword_prefixes(session: Session) -> list[str]:
    return [prefix for prefix in count_keywords(session) if prefix is not None]


def count_publication_types(session: Session) -> list[tuple[str | None, int]]:
    """Grouped case-insensitively; the first spelling seen is shown. Empty is None."""
    spellings: dict[str, str] = {}
    counts: Counter[str | None] = Counter()
    statement = select(Record.publication_type).order_by(Record.id)
    for value in session.scalars(statement):
        if not value:
            counts[None] += 1
            continue
        counts[spellings.setdefault(value.casefold(), value)] += 1
    return sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0] is None, (item[0] or "").casefold()),
    )


def count_records_per_source_file(
    session: Session,
) -> tuple[list[tuple[str, int]], int]:
    """Records from exactly one file count for that file; the second value counts
    records linked to several files. Ties keep import order."""
    statement = (
        select(RecordSource.record_id, SourceFile.id, SourceFile.filename)
        .join(RecordSource.source_file)
        .order_by(SourceFile.imported_at, SourceFile.id)
    )
    files: dict[int, str] = {}
    record_files: dict[int, set[int]] = defaultdict(set)
    for record_id, file_id, filename in session.execute(statement):
        files[file_id] = filename
        record_files[record_id].add(file_id)
    counts = Counter(next(iter(ids)) for ids in record_files.values() if len(ids) == 1)
    multiple = sum(len(ids) > 1 for ids in record_files.values())
    per_file = sorted(
        ((filename, counts[file_id]) for file_id, filename in files.items()),
        key=lambda item: -item[1],
    )
    return [(filename, count) for filename, count in per_file if count], multiple


def record_schema(record: Record, labels: list[LabelSchema]) -> RecordSchema:
    fields = {
        name: getattr(record, name)
        for name in RecordSchema.model_fields
        if name != "labels"
    }
    return RecordSchema.model_validate({**fields, "labels": labels})


def load_export_records(
    session: Session, ids: Collection[int] | None = None
) -> list[ExportRecord]:
    """`ids` None loads every record. A raw key the file's mapping doesn't list was
    set to ignore at import."""
    records_statement = select(Record).order_by(Record.id)
    sources_statement = (
        select(RecordSource.record_id, RecordSource.raw_fields, SourceFile)
        .join(RecordSource.source_file)
        .order_by(RecordSource.id)
    )
    labels_statement = select(Label).order_by(Label.id)
    if ids is not None:
        records_statement = records_statement.where(Record.id.in_(ids))
        sources_statement = sources_statement.where(RecordSource.record_id.in_(ids))
        labels_statement = labels_statement.where(Label.record_id.in_(ids))

    sources: dict[int, list[ExportSource]] = defaultdict(list)
    for record_id, raw_fields, source_file in session.execute(sources_statement):
        mapped = source_file.field_mapping.get("rows", {})
        sources[record_id].append(
            ExportSource(
                vendor=source_file.source,
                filename=source_file.filename,
                raw_fields=raw_fields,
                ignored_keys=frozenset(key for key in raw_fields if key not in mapped),
            )
        )
    labels: dict[int, list[LabelSchema]] = defaultdict(list)
    for label in session.scalars(labels_statement):
        labels[label.record_id].append(
            LabelSchema.model_validate(
                {"phase": label.phase, "screener": label.screener, "value": label.value}
            )
        )
    return [
        ExportRecord(
            id=record.id,
            record=record_schema(record, labels[record.id]),
            sources=sources[record.id],
        )
        for record in session.scalars(records_statement)
    ]
