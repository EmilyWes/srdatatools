import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, Base, SourceFile
from app.gui.activity_log import (
    clear_activity_log,
    log_import,
    log_import_failed,
    log_library_deleted,
    log_records_deleted,
    log_removal,
)


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


def test_log_import_failed__writes_warning_row_with_reason(session: Session) -> None:
    log_import_failed(session, "x.csv", "could not decode x.csv")
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Import failed:\nx.csv\nReason: could not decode x.csv"
    assert entry.action_type == "import"
    assert entry.status == "warning"


def test_log_removal__writes_remove_row_with_count(session: Session) -> None:
    log_removal(session, "x.csv", removed=2)
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Removed source file:\nx.csv\nRecords removed: 2"
    assert entry.action_type == "remove"
    assert entry.status == "ok"


def test_clear_activity_log__deletes_all_entries(session: Session) -> None:
    log_import(session, _source_file(row_count=3, skipped=0))
    log_removal(session, "x.csv", removed=2)
    session.commit()

    clear_activity_log(session)
    session.commit()

    assert session.query(ActivityLog).count() == 0


def test_log_library_deleted__writes_row_with_counts(session: Session) -> None:
    log_library_deleted(session, source_files=2, records=1204)
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == (
        "Deleted library\nSource files removed: 2\nRecords removed: 1204"
    )
    assert entry.action_type == "delete_library"
    assert entry.status == "ok"


def test_log_records_deleted__writes_row_with_count(session: Session) -> None:
    log_records_deleted(session, 3)
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Deleted records: 3"
    assert entry.action_type == "delete_records"
    assert entry.status == "ok"
