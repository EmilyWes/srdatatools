import datetime
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from app.db.models import Label, Record, RecordSource, SourceFile
from app.models.record import PartialDate
from app.models.record import Record as RecordSchema


def _build_record(schema: RecordSchema) -> Record:
    date = schema.publication_date or PartialDate()
    return Record(
        **schema.model_dump(exclude={"publication_date", "labels"}),
        publication_year=date.year,
        publication_month=date.month,
        publication_day=date.day,
    )


def store_parsed_rows(
    session: Session,
    *,
    filename: str,
    path: str | None,
    format: str,
    source: str | None = None,
    sheet: str | None = None,
    parsed_rows: Sequence[tuple[RecordSchema, dict[str, str]]],
    skipped_rows: Sequence[tuple[int, str]] = (),
    imported_at: datetime.datetime | None = None,
) -> SourceFile:
    source_file = SourceFile(
        filename=filename,
        path=path,
        format=format,
        source=source,
        sheet=sheet,
        imported_at=imported_at or datetime.datetime.now(),
        row_count=len(parsed_rows),
        skipped_rows=[
            {"row_number": row_number, "reason": reason}
            for row_number, reason in skipped_rows
        ],
    )

    for schema, raw_fields in parsed_rows:
        record = _build_record(schema)
        record.sources = [RecordSource(source_file=source_file, raw_fields=raw_fields)]
        record.labels = [
            Label(source_file=source_file, **label.model_dump())
            for label in schema.labels
        ]
        session.add(record)

    session.add(source_file)
    return source_file


def remove_source_file(session: Session, source_file: SourceFile) -> int:
    session.execute(delete(Label).where(Label.source_file_id == source_file.id))
    file_record_ids = select(RecordSource.record_id).where(
        RecordSource.source_file_id == source_file.id
    )
    other_record_ids = select(RecordSource.record_id).where(
        RecordSource.source_file_id != source_file.id
    )
    result = cast(
        CursorResult[Any],
        session.execute(
            delete(Record).where(
                Record.id.in_(file_record_ids), Record.id.not_in(other_record_ids)
            )
        ),
    )
    session.execute(
        delete(RecordSource).where(RecordSource.source_file_id == source_file.id)
    )
    session.delete(source_file)
    return result.rowcount


def delete_library(session: Session) -> tuple[int, int]:
    session.execute(delete(Label))
    session.execute(delete(RecordSource))
    records = cast(CursorResult[Any], session.execute(delete(Record)))
    source_files = cast(CursorResult[Any], session.execute(delete(SourceFile)))
    return source_files.rowcount, records.rowcount
