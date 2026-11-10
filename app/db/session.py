import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import platformdirs
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def project_root() -> Path:
    """A frozen build unpacks its bundled alembic.ini and migrations to _MEIPASS."""
    frozen_root: str | None = getattr(sys, "_MEIPASS", None)
    if frozen_root is not None:
        return Path(frozen_root)
    return Path(__file__).resolve().parent.parent.parent


def default_db_path() -> Path:
    data_dir = Path(platformdirs.user_data_dir("srdatatools", appauthor=False))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "srdatatools.db"


def run_migrations(db_path: Path | None = None) -> None:
    resolved_path = db_path if db_path is not None else default_db_path()
    config = Config(project_root() / "alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{resolved_path}")
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def get_engine(db_path: Path | None = None) -> Engine:
    resolved_path = db_path if db_path is not None else default_db_path()
    return create_engine(f"sqlite:///{resolved_path}")


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
