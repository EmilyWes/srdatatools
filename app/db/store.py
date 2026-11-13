import datetime
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session, selectinload

from app.cleaning.options import CleaningOptions
from app.cleaning.steps import (
    STEP_NAMES,
    CleaningContext,
    clean_record,
    file_separators,
)
from app.db.models import Label, Record, RecordSource, SourceFile
from app.db.queries import record_schema
from app.models.record import Record as RecordSchema
from app.parsers.mapping import FieldMapping

# Cleaning doesn't touch these, and they aren't plain columns.
_NOT_CLEANED = {"labels"}


def _build_record(schema: RecordSchema) -> Record:
    return Record(**schema.model_dump(exclude={"labels"}))


def store_parsed_rows(
    session: Session,
    *,
    filename: str,
    path: str | None,
    format: str,
    sources: Sequence[str] = (),
    sheet: str | None = None,
    parsed_rows: Sequence[tuple[RecordSchema, dict[str, str]]],
    skipped_rows: Sequence[tuple[int, str]] = (),
    imported_at: datetime.datetime | None = None,
) -> SourceFile:
    source_file = SourceFile(
        filename=filename,
        path=path,
        format=format,
        sources=list(sources),
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


def delete_records(session: Session, ids: Collection[int]) -> int:
    session.execute(delete(Label).where(Label.record_id.in_(ids)))
    session.execute(delete(RecordSource).where(RecordSource.record_id.in_(ids)))
    result = cast(
        CursorResult[Any], session.execute(delete(Record).where(Record.id.in_(ids)))
    )
    return result.rowcount


def _context(
    source: RecordSource | None,
    separators: tuple[str | None, str | None, str | None, str | None],
) -> CleaningContext:
    if source is None:
        return CleaningContext(
            names_separator=separators[0],
            affiliations_separator=separators[1],
            ids_separator=separators[2],
            keywords_separator=separators[3],
        )
    source_file = source.source_file
    return CleaningContext(
        raw_fields=source.raw_fields,
        mapping=FieldMapping.model_validate(source_file.field_mapping),
        use_first=tuple(source_file.quirk_choices.get("use_first", [])),
        names_separator=separators[0],
        affiliations_separator=separators[1],
        ids_separator=separators[2],
        keywords_separator=separators[3],
    )


def clean_records(
    session: Session, options: CleaningOptions, ids: Collection[int] | None = None
) -> tuple[int, int, Counter[str]]:
    """`ids` None cleans every record. A record is cleaned with its first source
    file's raw fields and mapping, and author separators are sniffed per source
    file. Returns the records cleaned, the records changed and the changes per
    step, in the order the steps run."""
    statement = (
        select(Record)
        .options(selectinload(Record.sources).selectinload(RecordSource.source_file))
        .order_by(Record.id)
    )
    if ids is not None:
        statement = statement.where(Record.id.in_(ids))
    records = session.scalars(statement).all()

    sources = {
        record.id: min(record.sources, key=lambda s: s.id, default=None)
        for record in records
    }
    schemas = {record.id: record_schema(record, []) for record in records}
    per_file: dict[int | None, list[RecordSchema]] = defaultdict(list)
    for record in records:
        source = sources[record.id]
        per_file[source.source_file_id if source else None].append(schemas[record.id])
    separators = {
        file_id: file_separators(file_schemas, options)
        for file_id, file_schemas in per_file.items()
    }

    changed = 0
    per_step: Counter[str] = Counter()
    for record in records:
        source = sources[record.id]
        context = _context(
            source, separators[source.source_file_id if source else None]
        )
        cleaned, steps = clean_record(schemas[record.id], context, options)
        if not steps:
            continue
        changed += 1
        per_step.update(steps)
        for name, value in cleaned.model_dump(exclude=_NOT_CLEANED).items():
            if getattr(record, name) != value:
                setattr(record, name, value)
    in_order = Counter(
        {name: per_step[name] for name in STEP_NAMES if name in per_step}
    )
    return len(records), changed, in_order
