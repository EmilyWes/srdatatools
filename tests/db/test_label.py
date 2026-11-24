import datetime

import pytest
from sqlalchemy.orm import Session

from app.db.label import count_label_values, list_label_columns, list_record_labels
from app.db.models import Label, Record, SourceFile


def _source_file(
    filename: str, source: str | None, imported_at: datetime.datetime
) -> SourceFile:
    return SourceFile(
        filename=filename,
        path=None,
        format="ris",
        sources=[source] if source is not None else [],
        imported_at=imported_at,
        row_count=None,
    )


@pytest.fixture
def labeled(session: Session) -> Session:
    source_file = _source_file("asreview.csv", None, datetime.datetime(2026, 1, 1))
    first = Record(id=1)
    second = Record(id=2)

    def label(record: Record, phase: str, screener: str, value: str) -> Label:
        return Label(
            record=record,
            source_file=source_file,
            phase=phase,
            screener=screener,
            value=value,
        )

    session.add_all(
        [
            label(first, "tiab", "Emily", "include"),
            label(first, "ft", "screener 1", "exclude"),
            label(second, "tiab", "Emily", "exclude"),
            label(second, "tiab", "Emily", "maybe"),
            Record(id=3),
        ]
    )
    session.commit()
    return session


def test_list_label_columns__distinct_pairs_in_first_seen_order(
    labeled: Session,
) -> None:
    assert list_label_columns(labeled) == [("tiab", "Emily"), ("ft", "screener 1")]


def test_list_label_columns__empty_without_labels(session: Session) -> None:
    assert list_label_columns(session) == []


def test_list_record_labels__values_per_record_and_pair(labeled: Session) -> None:
    assert list_record_labels(labeled) == {
        1: {("tiab", "Emily"): ["include"], ("ft", "screener 1"): ["exclude"]},
        2: {("tiab", "Emily"): ["exclude", "maybe"]},
    }


def test_count_label_values__records_per_value_with_missing_as_unlabeled(
    labeled: Session,
) -> None:
    assert count_label_values(labeled) == {
        ("tiab", "Emily"): {"include": 1, "exclude": 1, "maybe": 1, "unlabeled": 1},
        ("ft", "screener 1"): {"exclude": 1, "unlabeled": 2},
    }


def test_count_label_values__empty_without_labels(session: Session) -> None:
    assert count_label_values(session) == {}
