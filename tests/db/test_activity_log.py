import datetime

from sqlalchemy.orm import Session

from app.db.activity_log import add_activity, clear_activity_log, list_activity_log
from app.db.models import ActivityLog


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
