import datetime
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.db.models import Record, RecordSource, SourceFile
from app.models.record import PartialDate
from app.models.record import Record as RecordSchema


def _build_record(schema: RecordSchema) -> Record:
    date = schema.publication_date or PartialDate()
    return Record(
        **schema.model_dump(exclude={"publication_date"}),
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
    parsed_rows: Sequence[tuple[RecordSchema, dict[str, str]]],
    skipped_rows: Sequence[tuple[int, str]] = (),
    imported_at: datetime.datetime | None = None,
) -> SourceFile:
    source_file = SourceFile(
        filename=filename,
        path=path,
        format=format,
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
        session.add(record)

    session.add(source_file)
    return source_file
