import datetime
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ActivityLog, Base, Record, RecordSource, SourceFile


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_record__create_with_authors_and_source(session: Session) -> None:
    source_file = SourceFile(
        filename="pubmed_export.nbib",
        path="/imports/pubmed_export.nbib",
        format="nbib",
        imported_at=datetime.datetime(2026, 1, 1),
        row_count=1,
    )
    authors = [
        {"family_name": "Smith", "orcid": "0000-0001-2345-6789"},
        {"family_name": "Doe"},
    ]
    record = Record(title="A Study of Things", doi="10.1000/abc", authors=authors)
    record.sources = [
        RecordSource(source_file=source_file, raw_fields={"TI": "A Study of Things"})
    ]
    session.add(record)
    session.commit()

    fetched = session.query(Record).one()
    assert fetched.title == "A Study of Things"
    assert fetched.authors == authors
    assert fetched.sources[0].source_file.filename == "pubmed_export.nbib"
    assert fetched.sources[0].raw_fields == {"TI": "A Study of Things"}


def test_record__authors_and_skipped_rows_default_to_empty_lists(
    session: Session,
) -> None:
    session.add(Record(title="No Authors"))
    session.add(
        SourceFile(
            filename="export.csv",
            path=None,
            format="csv",
            imported_at=datetime.datetime(2026, 1, 1),
            row_count=0,
        )
    )
    session.commit()

    assert session.query(Record).one().authors == []
    assert session.query(SourceFile).one().skipped_rows == []


def test_record__multiple_null_dois_allowed(session: Session) -> None:
    session.add_all([Record(title="First"), Record(title="Second")])
    session.commit()

    assert session.query(Record).count() == 2


def test_activity_log__linked_to_record(session: Session) -> None:
    record = Record(title="A Study of Things")
    session.add(record)
    session.flush()

    session.add(
        ActivityLog(
            timestamp=datetime.datetime(2026, 1, 1),
            action_type="import",
            message="Imported 1 record from pubmed_export.nbib",
            record_id=record.id,
        )
    )
    session.commit()

    log_entry = session.query(ActivityLog).one()
    assert log_entry.record_id == record.id
    assert log_entry.action_type == "import"


def test_activity_log__record_id_optional_for_summary_actions(session: Session) -> None:
    session.add(
        ActivityLog(
            timestamp=datetime.datetime(2026, 1, 1),
            action_type="import",
            message="Imported 998 records, skipped 2",
            record_id=None,
        )
    )
    session.commit()

    log_entry = session.query(ActivityLog).one()
    assert log_entry.record_id is None
