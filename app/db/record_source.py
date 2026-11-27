from collections import Counter, defaultdict
from collections.abc import Collection

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RecordSource, SourceFile


def list_record_sources(session: Session) -> dict[int, list[str | None]]:
    statement = (
        select(RecordSource.record_id, SourceFile.sources)
        .join(RecordSource.source_file)
        .order_by(RecordSource.id)
    )
    sources: dict[int, list[str | None]] = defaultdict(list)
    for record_id, file_sources in session.execute(statement):
        sources[record_id].extend(file_sources or [None])
    return sources


def count_records_for_file(session: Session, source_file_id: int) -> int:
    statement = select(func.count(func.distinct(RecordSource.record_id))).where(
        RecordSource.source_file_id == source_file_id
    )
    return session.scalar(statement) or 0


def list_record_ids_for_files(
    session: Session, source_file_ids: Collection[int]
) -> set[int]:
    statement = select(RecordSource.record_id).where(
        RecordSource.source_file_id.in_(source_file_ids)
    )
    return set(session.scalars(statement))


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
