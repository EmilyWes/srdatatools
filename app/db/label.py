from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Label
from app.db.record import count_records


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
