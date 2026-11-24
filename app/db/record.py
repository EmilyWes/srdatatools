from collections.abc import Collection, Mapping, Sequence
from typing import Any
from typing import cast as typing_cast

from sqlalchemy import (
    JSON,
    ColumnElement,
    CursorResult,
    String,
    and_,
    case,
    cast,
    delete,
    func,
    select,
)
from sqlalchemy.orm import InstrumentedAttribute, Session, selectinload

from app.db.models import Label, Record, RecordSource
from app.models.record import Label as LabelSchema
from app.models.record import Record as RecordSchema

_EMPTY_JSON = ("[]", "{}", "null")


def list_record_rows(session: Session, fields: Sequence[str]) -> list[dict[str, Any]]:
    statement = select(
        Record.id, *(getattr(Record, field) for field in fields)
    ).order_by(Record.id)
    return [dict(row) for row in session.execute(statement).mappings()]


def count_records(session: Session) -> int:
    return session.scalar(select(func.count(Record.id))) or 0


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


def record_schema(record: Record, labels: list[LabelSchema]) -> RecordSchema:
    fields = {
        name: getattr(record, name)
        for name in RecordSchema.model_fields
        if name != "labels"
    }
    return RecordSchema.model_validate({**fields, "labels": labels})


def load_records(session: Session, ids: Collection[int] | None = None) -> list[Record]:
    """`ids` None loads every record."""
    statement = (
        select(Record)
        .options(
            selectinload(Record.sources).selectinload(RecordSource.source_file),
            selectinload(Record.labels),
        )
        .order_by(Record.id)
    )
    if ids is not None:
        statement = statement.where(Record.id.in_(ids))
    return list(session.scalars(statement))


def delete_records(session: Session, ids: Collection[int]) -> int:
    session.execute(delete(Label).where(Label.record_id.in_(ids)))
    session.execute(delete(RecordSource).where(RecordSource.record_id.in_(ids)))
    result = typing_cast(
        CursorResult[Any], session.execute(delete(Record).where(Record.id.in_(ids)))
    )
    return result.rowcount


def update_records(session: Session, changes: Mapping[int, Mapping[str, Any]]) -> None:
    for record_id, fields in changes.items():
        record = session.get(Record, record_id)
        for name, value in fields.items():
            setattr(record, name, value)
