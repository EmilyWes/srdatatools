import sqlite3
from pathlib import Path

import platformdirs
import pytest

from app.db.session import default_db_path, run_migrations

EXPECTED_TABLES = {
    "activity_log",
    "author",
    "record",
    "record_author",
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


def test_run_migrations__defaults_to_default_db_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fallback_path = tmp_path / "srdatatools.db"
    monkeypatch.setattr("app.db.session.default_db_path", lambda: fallback_path)

    run_migrations()

    assert fallback_path.exists()
