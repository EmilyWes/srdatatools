from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceFile


def list_source_files(session: Session) -> list[SourceFile]:
    statement = select(SourceFile).order_by(SourceFile.imported_at)
    return list(session.scalars(statement))
