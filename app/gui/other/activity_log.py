from collections import Counter

from sqlalchemy.orm import Session

from app.db.activity_log import add_activity
from app.db.models import ActivityLog, SourceFile
from app.helpers.format import format_count


def log_import(session: Session, source_file: SourceFile) -> ActivityLog:
    skipped = len(source_file.skipped_rows)
    return add_activity(
        session,
        "import",
        f"Imported from:\n{source_file.filename}\n"
        f"Processed: {source_file.row_count}\nSkipped: {skipped}",
        status="warning" if skipped else "ok",
        timestamp=source_file.imported_at,
    )


def log_import_failed(session: Session, filename: str, reason: str) -> ActivityLog:
    return add_activity(
        session,
        "import",
        f"Import failed:\n{filename}\nReason: {reason}",
        status="warning",
    )


def log_removal(session: Session, filename: str, removed: int) -> ActivityLog:
    return add_activity(
        session,
        "remove",
        f"Removed source file:\n{filename}\nRecords removed: {removed}",
    )


def log_library_deleted(
    session: Session, source_files: int, records: int
) -> ActivityLog:
    return add_activity(
        session,
        "delete_library",
        f"Deleted library\nSource files removed: {source_files}\n"
        f"Records removed: {records}",
    )


def log_records_deleted(session: Session, count: int) -> ActivityLog:
    return add_activity(session, "delete_records", f"Deleted records: {count}")


def log_export(
    session: Session, filename: str, records: int, cut: int = 0, removed: int = 0
) -> ActivityLog:
    message = f"Exported to:\n{filename}\nRecords: {format_count(records)}"
    if cut:
        message += f"\nValues cut: {format_count(cut)}"
    if removed:
        message += f"\nControl characters removed: {format_count(removed)}"
    return add_activity(
        session, "export", message, status="warning" if cut or removed else "ok"
    )


def log_export_failed(session: Session, filename: str, reason: str) -> ActivityLog:
    return add_activity(
        session,
        "export",
        f"Export failed:\n{filename}\nReason: {reason}",
        status="warning",
    )


def log_cleaning(
    session: Session, records: int, changed: int, per_step: Counter[str]
) -> ActivityLog:
    """One line per step that changed records, in per_step's order."""
    noun = "record" if records == 1 else "records"
    lines = [
        f"Cleaned {format_count(records)} {noun}: {format_count(changed)} changed",
        *(f"{step}: {format_count(count)}" for step, count in per_step.items()),
    ]
    return add_activity(session, "clean", "\n".join(lines))
