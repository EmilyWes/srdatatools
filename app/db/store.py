import datetime
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.db.models import Record, RecordSource, SourceFile
from app.models.record import Record as RecordSchema


def _build_record(schema: RecordSchema) -> Record:
    publication_year = None
    publication_month = None
    publication_day = None
    if schema.publication_date is not None:
        publication_year = schema.publication_date.year
        publication_month = schema.publication_date.month
        publication_day = schema.publication_date.day

    return Record(
        title=schema.title,
        abstract=schema.abstract,
        publication_year=publication_year,
        publication_month=publication_month,
        publication_day=publication_day,
        journal=schema.journal,
        conference_name=schema.conference_name,
        volume=schema.volume,
        issue=schema.issue,
        pages=schema.pages,
        doi=schema.doi,
        pmid=schema.pmid,
        issn=schema.issn,
        isbn=schema.isbn,
        other_ids=dict(schema.other_ids),
        publication_type=schema.publication_type,
        keywords=list(schema.keywords),
        language=schema.language,
        publisher=schema.publisher,
        url=schema.url,
        notes=schema.notes,
    )


def store_parsed_rows(
    session: Session,
    *,
    filename: str,
    path: str | None,
    format: str,
    parsed_rows: Sequence[tuple[RecordSchema, dict[str, str]]],
    imported_at: datetime.datetime | None = None,
) -> SourceFile:
    resolved_imported_at = imported_at or datetime.datetime.now()

    source_file = SourceFile(
        filename=filename,
        path=path,
        format=format,
        imported_at=resolved_imported_at,
        row_count=len(parsed_rows),
    )

    for schema, raw_fields in parsed_rows:
        record = _build_record(schema)
        record.sources = [
            RecordSource(
                source_file=source_file,
                raw_fields=raw_fields,
                imported_at=resolved_imported_at,
            )
        ]
        session.add(record)

    session.add(source_file)
    return source_file
