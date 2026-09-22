import sqlite3
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

EXPECTED_TABLES = {
    "activity_log",
    "author",
    "record",
    "record_author",
    "record_source",
    "source_file",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_alembic_upgrade_head__creates_all_phase_1_tables() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "migration_test.db"
        config = Config(PROJECT_ROOT / "alembic.ini")
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        command.upgrade(config, "head")

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
