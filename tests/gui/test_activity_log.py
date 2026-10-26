import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, Base, SourceFile
from app.gui.activity_log import log_import


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _source_file(row_count: int, skipped: int) -> SourceFile:
    return SourceFile(
        filename="x.csv",
        path=None,
        format="csv",
        imported_at=datetime.datetime(2026, 1, 1, 9, 5),
        row_count=row_count,
        skipped_rows=[
            {"row_number": n, "reason": "row is blank"} for n in range(skipped)
        ],
    )


def test_log_import__writes_import_row_with_counts(session: Session) -> None:
    log_import(session, _source_file(row_count=3, skipped=1))
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Imported from:\nx.csv\nProcessed: 3\nSkipped: 1"
    assert entry.action_type == "import"
    assert entry.timestamp == datetime.datetime(2026, 1, 1, 9, 5)
    assert entry.record_id is None


def test_log_import__zero_skipped_still_shown(session: Session) -> None:
    entry = log_import(session, _source_file(row_count=2, skipped=0))

    assert entry.message == "Imported from:\nx.csv\nProcessed: 2\nSkipped: 0"


def test_log_import__status_warning_when_rows_skipped(session: Session) -> None:
    entry = log_import(session, _source_file(row_count=3, skipped=1))

    assert entry.status == "warning"


def test_log_import__status_ok_when_nothing_skipped(session: Session) -> None:
    entry = log_import(session, _source_file(row_count=3, skipped=0))

    assert entry.status == "ok"
