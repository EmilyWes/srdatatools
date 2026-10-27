import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, SourceFile


def log_import(session: Session, source_file: SourceFile) -> ActivityLog:
    skipped = len(source_file.skipped_rows)
    entry = ActivityLog(
        timestamp=source_file.imported_at,
        action_type="import",
        message=(
            f"Imported from:\n{source_file.filename}\n"
            f"Processed: {source_file.row_count}\nSkipped: {skipped}"
        ),
        status="warning" if skipped else "ok",
    )
    session.add(entry)
    return entry


def log_removal(session: Session, filename: str, removed: int) -> ActivityLog:
    entry = ActivityLog(
        timestamp=datetime.datetime.now(),
        action_type="remove",
        message=f"Removed source file:\n{filename}\nRecords removed: {removed}",
    )
    session.add(entry)
    return entry


def log_library_deleted(
    session: Session, source_files: int, records: int
) -> ActivityLog:
    entry = ActivityLog(
        timestamp=datetime.datetime.now(),
        action_type="delete_library",
        message=(
            f"Deleted library\nSource files removed: {source_files}\n"
            f"Records removed: {records}"
        ),
    )
    session.add(entry)
    return entry


def clear_activity_log(session: Session) -> None:
    session.execute(delete(ActivityLog))
