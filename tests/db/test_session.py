import logging
import sqlite3
from pathlib import Path

import platformdirs
import pytest

from app.db.session import default_db_path, run_migrations

EXPECTED_TABLES = {
    "activity_log",
    "app_settings",
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


def test_run_migrations__source_file_has_source_column(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_test.db"

    run_migrations(db_path)

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in connection.execute("pragma table_info(source_file)")
        }
    finally:
        connection.close()

    assert "source" in columns


def test_run_migrations__source_file_has_nullable_sheet_column(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "migration_test.db"

    run_migrations(db_path)

    connection = sqlite3.connect(db_path)
    try:
        notnull_by_column = {
            row[1]: row[3]
            for row in connection.execute("pragma table_info(source_file)")
        }
    finally:
        connection.close()

    assert notnull_by_column["sheet"] == 0


def test_run_migrations__source_file_mapping_columns_default_to_empty(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "migration_test.db"

    run_migrations(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "insert into source_file (filename, format, imported_at, skipped_rows)"
            " values ('export.ris', 'ris', '2026-01-01 00:00:00', '[]')"
        )
        row = connection.execute(
            "select field_mapping, suggested_mapping, file_summary from source_file"
        ).fetchone()
    finally:
        connection.close()

    assert row == ("{}", "{}", "{}")


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
