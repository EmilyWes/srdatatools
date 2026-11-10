import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, SourceFile
from app.gui.format import format_count


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


def log_import_failed(session: Session, filename: str, reason: str) -> ActivityLog:
    entry = ActivityLog(
        timestamp=datetime.datetime.now(),
        action_type="import",
        message=f"Import failed:\n{filename}\nReason: {reason}",
        status="warning",
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


def log_records_deleted(session: Session, count: int) -> ActivityLog:
    entry = ActivityLog(
        timestamp=datetime.datetime.now(),
        action_type="delete_records",
        message=f"Deleted records: {count}",
    )
    session.add(entry)
    return entry


def log_export(session: Session, filename: str, records: int) -> ActivityLog:
    entry = ActivityLog(
        timestamp=datetime.datetime.now(),
        action_type="export",
        message=f"Exported to:\n{filename}\nRecords: {format_count(records)}",
    )
    session.add(entry)
    return entry


def log_export_failed(session: Session, filename: str, reason: str) -> ActivityLog:
    entry = ActivityLog(
        timestamp=datetime.datetime.now(),
        action_type="export",
        message=f"Export failed:\n{filename}\nReason: {reason}",
        status="warning",
    )
    session.add(entry)
    return entry


def clear_activity_log(session: Session) -> None:
    session.execute(delete(ActivityLog))
