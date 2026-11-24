from collections import Counter, defaultdict
from collections.abc import Collection
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import RecordSource
from app.db.record import load_records, record_schema, update_records
from app.gui.cleaning.options import CleaningOptions
from app.gui.cleaning.steps import (
    STEP_NAMES,
    CleaningContext,
    clean_record,
    file_separators,
)
from app.models.record import Record as RecordSchema
from app.parsers.mapping import FieldMapping

# Cleaning doesn't touch these, and they aren't plain columns.
_NOT_CLEANED = {"labels"}


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
        use_first=tuple(source_file.option_choices.get("use_first", [])),
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
    records = load_records(session, ids)

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

    changes: dict[int, dict[str, Any]] = {}
    per_step: Counter[str] = Counter()
    for record in records:
        source = sources[record.id]
        context = _context(
            source, separators[source.source_file_id if source else None]
        )
        cleaned, steps = clean_record(schemas[record.id], context, options)
        if not steps:
            continue
        per_step.update(steps)
        changes[record.id] = {
            name: value
            for name, value in cleaned.model_dump(exclude=_NOT_CLEANED).items()
            if getattr(record, name) != value
        }
    update_records(session, changes)
    in_order = Counter(
        {name: per_step[name] for name in STEP_NAMES if name in per_step}
    )
    return len(records), len(changes), in_order
