import datetime
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ActivityLog, Base, SourceFile
from app.db.queries import list_activity_log, list_source_files


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


def test_list_source_files__empty_when_none_imported(session: Session) -> None:
    assert list_source_files(session) == []


def test_list_source_files__returns_files_ordered_by_import_time(
    session: Session,
) -> None:
    newer = SourceFile(
        filename="scopus_export.csv",
        path=None,
        format="csv",
        imported_at=datetime.datetime(2026, 2, 1),
        row_count=10,
    )
    older = SourceFile(
        filename="pubmed_export.nbib",
        path=None,
        format="nbib",
        imported_at=datetime.datetime(2026, 1, 1),
        row_count=5,
    )
    session.add_all([newer, older])
    session.commit()

    result = list_source_files(session)

    assert [source_file.filename for source_file in result] == [
        "pubmed_export.nbib",
        "scopus_export.csv",
    ]


def test_list_activity_log__empty_when_nothing_logged(session: Session) -> None:
    assert list_activity_log(session) == []


def test_list_activity_log__returns_entries_oldest_first(session: Session) -> None:
    session.add_all(
        [
            ActivityLog(
                timestamp=datetime.datetime(2026, 2, 1),
                action_type="import",
                message="second",
            ),
            ActivityLog(
                timestamp=datetime.datetime(2026, 1, 1),
                action_type="import",
                message="first",
            ),
        ]
    )
    session.commit()

    result = list_activity_log(session)

    assert [entry.message for entry in result] == ["first", "second"]
