import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import ActivityLog


def add_activity(
    session: Session,
    action_type: str,
    message: str,
    status: str = "ok",
    timestamp: datetime.datetime | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        timestamp=timestamp or datetime.datetime.now(),
        action_type=action_type,
        message=message,
        status=status,
    )
    session.add(entry)
    return entry


def clear_activity_log(session: Session) -> None:
    session.execute(delete(ActivityLog))
