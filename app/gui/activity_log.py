from sqlalchemy.orm import Session

from app.db.models import ActivityLog, SourceFile


def log_import(session: Session, source_file: SourceFile) -> ActivityLog:
    count = source_file.row_count
    noun = "record" if count == 1 else "records"
    entry = ActivityLog(
        timestamp=source_file.imported_at,
        action_type="import",
        message=(
            f"Imported {count} {noun} from {source_file.filename},"
            f" {len(source_file.skipped_rows)} skipped"
        ),
    )
    session.add(entry)
    return entry
