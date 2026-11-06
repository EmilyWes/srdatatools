import logging
import shutil
import sqlite3
import sys
from pathlib import Path

import platformdirs
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db.models import Base
from app.db.session import default_db_path, project_root, run_migrations

EXPECTED_TABLES = {
    "activity_log",
    "app_settings",
    "label",
    "record",
    "record_source",
    "source_file",
}


def test_default_db_path__resolves_under_platform_user_data_dir() -> None:
    expected_dir = platformdirs.user_data_path("srdatatools", appauthor=False)

    db_path = default_db_path()

    assert db_path.parent == expected_dir
    assert db_path.name == "srdatatools.db"
    assert db_path.parent.is_dir()


def test_run_migrations__creates_all_tables_at_given_path(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_test.db"

    run_migrations(db_path)

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
    finally:
        connection.close()

    assert EXPECTED_TABLES <= tables


def test_run_migrations__schema_matches_the_models(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_test.db"
    run_migrations(db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_server_default": True}
        )
        differences = compare_metadata(context, Base.metadata)
    engine.dispose()

    assert differences == []


def test_run_migrations__activity_log_status_defaults_to_ok(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_test.db"

    run_migrations(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "insert into activity_log (timestamp, action_type, message)"
            " values ('2026-01-01 00:00:00', 'import', 'Imported 1 record')"
        )
        status = connection.execute("select status from activity_log").fetchone()[0]
    finally:
        connection.close()

    assert status == "ok"


def test_run_migrations__leaves_app_logging_configuration_alone(
    tmp_path: Path,
) -> None:
    app_logger = logging.getLogger("app.parsers.csv_")
    root = logging.getLogger()
    handlers_before, level_before = root.handlers[:], root.level

    run_migrations(tmp_path / "migration_test.db")

    assert app_logger.disabled is False
    assert root.handlers == handlers_before
    assert root.level == level_before


def test_run_migrations__defaults_to_default_db_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fallback_path = tmp_path / "srdatatools.db"
    monkeypatch.setattr("app.db.session.default_db_path", lambda: fallback_path)

    run_migrations()

    assert fallback_path.exists()


def test_project_root__is_repo_root_when_not_frozen() -> None:
    assert (project_root() / "alembic.ini").is_file()


def test_run_migrations__frozen_reads_bundled_alembic_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mirrors the data layout packaging/pyinstaller.spec bundles into _MEIPASS."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copy(project_root() / "alembic.ini", bundle / "alembic.ini")
    shutil.copytree(
        project_root() / "app" / "db" / "migrations",
        bundle / "app" / "db" / "migrations",
    )
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    db_path = tmp_path / "frozen.db"

    run_migrations(db_path)

    assert project_root() == bundle
    assert db_path.exists()
