import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.activity_log import add_activity, clear_activity_log
from app.db.models import ActivityLog, Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_add_activity__defaults_to_now_and_ok(session: Session) -> None:
    before = datetime.datetime.now()

    entry = add_activity(session, "import", "Imported")
    session.commit()

    assert session.query(ActivityLog).one() is entry
    assert (entry.action_type, entry.message, entry.status) == (
        "import",
        "Imported",
        "ok",
    )
    assert before <= entry.timestamp <= datetime.datetime.now()


def test_add_activity__keeps_given_timestamp_and_status(session: Session) -> None:
    timestamp = datetime.datetime(2026, 1, 1, 9, 5)

    entry = add_activity(session, "export", "Failed", "warning", timestamp)

    assert (entry.timestamp, entry.status) == (timestamp, "warning")


def test_clear_activity_log__deletes_all_entries(session: Session) -> None:
    add_activity(session, "import", "Imported")
    add_activity(session, "remove", "Removed")
    session.commit()

    clear_activity_log(session)
    session.commit()

    assert session.query(ActivityLog).count() == 0
