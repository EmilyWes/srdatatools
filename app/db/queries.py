from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ActivityLog, Record, RecordSource, SourceFile


def list_source_files(session: Session) -> list[SourceFile]:
    statement = select(SourceFile).order_by(SourceFile.imported_at)
    return list(session.scalars(statement))


def list_activity_log(session: Session) -> list[ActivityLog]:
    statement = select(ActivityLog).order_by(ActivityLog.timestamp, ActivityLog.id)
    return list(session.scalars(statement))


def list_records(session: Session) -> list[Record]:
    statement = (
        select(Record)
        .options(selectinload(Record.sources).selectinload(RecordSource.source_file))
        .order_by(Record.id)
    )
    return list(session.scalars(statement))


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


def count_records_per_year(session: Session) -> list[tuple[int | None, int]]:
    statement = (
        select(Record.publication_year, func.count(Record.id))
        .group_by(Record.publication_year)
        .order_by(Record.publication_year.asc().nulls_last())
    )
    return [(year, count) for year, count in session.execute(statement)]
