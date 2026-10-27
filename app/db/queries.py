from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, Label, Record, RecordSource, SourceFile


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


def count_records_per_source(session: Session) -> list[tuple[str | None, int]]:
    statement = (
        select(SourceFile.source, func.count(func.distinct(RecordSource.record_id)))
        .join(RecordSource.source_file)
        .group_by(SourceFile.source)
        .order_by(SourceFile.source.asc().nulls_last())
    )
    return [(source, count) for source, count in session.execute(statement)]


def count_records_per_file(session: Session) -> list[tuple[str, int]]:
    statement = (
        select(SourceFile.filename, func.count(func.distinct(RecordSource.record_id)))
        .join(RecordSource.source_file)
        .group_by(SourceFile.id)
        .order_by(SourceFile.imported_at)
    )
    return [(filename, count) for filename, count in session.execute(statement)]


def count_records_for_file(session: Session, source_file_id: int) -> int:
    statement = select(func.count(func.distinct(RecordSource.record_id))).where(
        RecordSource.source_file_id == source_file_id
    )
    return session.scalar(statement) or 0


def count_records_per_year(session: Session) -> list[tuple[int | None, int]]:
    statement = (
        select(Record.publication_year, func.count(Record.id))
        .group_by(Record.publication_year)
        .order_by(Record.publication_year.asc().nulls_last())
    )
    return [(year, count) for year, count in session.execute(statement)]
