import datetime
from collections import Counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.activity_log import (
    clear_activity_log,
    log_cleaning,
    log_export,
    log_export_failed,
    log_import,
    log_import_failed,
    log_library_deleted,
    log_records_deleted,
    log_removal,
)
from app.db.models import ActivityLog, Base, SourceFile


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


def test_log_export__writes_ok_row_with_filename_and_count(session: Session) -> None:
    log_export(session, "library.csv", records=1234)
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Exported to:\nlibrary.csv\nRecords: 1.234"
    assert entry.action_type == "export"
    assert entry.status == "ok"


def test_log_export_failed__writes_warning_row_with_reason(session: Session) -> None:
    log_export_failed(session, "library.csv", "Permission denied")
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Export failed:\nlibrary.csv\nReason: Permission denied"
    assert entry.action_type == "export"
    assert entry.status == "warning"


def test_log_export__cut_values_make_a_warning(session: Session) -> None:
    log_export(session, "library.csv", records=10, cut=3)
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Exported to:\nlibrary.csv\nRecords: 10\nValues cut: 3"
    assert entry.status == "warning"


def test_log_cleaning__one_line_per_step_in_given_order(session: Session) -> None:
    per_step = Counter({"Split authors": 300, "Pages set": 4000})

    log_cleaning(session, 10000, 4012, per_step)
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.action_type == "clean"
    assert entry.status == "ok"
    assert entry.message == (
        "Cleaned 10.000 records: 4.012 changed\nSplit authors: 300\nPages set: 4.000"
    )


def test_log_cleaning__nothing_changed(session: Session) -> None:
    log_cleaning(session, 5, 0, Counter())

    assert session.query(ActivityLog).one().message == "Cleaned 5 records: 0 changed"


def test_log_cleaning__one_record_is_singular(session: Session) -> None:
    log_cleaning(session, 1, 0, Counter())

    assert session.query(ActivityLog).one().message == "Cleaned 1 record: 0 changed"
