from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.db.settings import set_setting
from app.export.options import (
    ExportOptions,
    default_path,
    load_folder,
    load_options,
    reset_options,
    save_folder,
    save_options,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_load_folder__documents_when_unset(session: Session) -> None:
    assert load_folder(session) == Path.home() / "Documents"


def test_save_folder__round_trips(session: Session, tmp_path: Path) -> None:
    save_folder(session, tmp_path)
    session.commit()

    assert load_folder(session) == tmp_path


def test_load_folder__documents_when_saved_folder_is_gone(
    session: Session, tmp_path: Path
) -> None:
    save_folder(session, tmp_path / "gone")
    session.commit()

    assert load_folder(session) == Path.home() / "Documents"


def test_default_path__library_when_free(tmp_path: Path) -> None:
    assert default_path(tmp_path) == tmp_path / "library.csv"


def test_default_path__numbers_past_existing_files(tmp_path: Path) -> None:
    (tmp_path / "library.csv").touch()
    (tmp_path / "library_1.csv").touch()

    assert default_path(tmp_path) == tmp_path / "library_2.csv"


def test_load_options__defaults_when_unset(session: Session) -> None:
    assert load_options(session) == ExportOptions()


def test_save_options__round_trips(session: Session) -> None:
    options = ExportOptions(delimiter="\t", encoding="utf-8", original_data=True)

    save_options(session, options)
    session.commit()

    assert load_options(session) == options


def test_reset_options__back_to_defaults(session: Session) -> None:
    save_options(session, ExportOptions(delimiter=";"))
    reset_options(session)
    session.commit()

    assert load_options(session) == ExportOptions()


def test_load_options__defaults_when_stored_value_is_invalid(session: Session) -> None:
    set_setting(session, "export_options", '{"delimiter": "|"}')
    session.commit()

    assert load_options(session) == ExportOptions()


def test_load_options__defaults_to_pythons_csv_field_limit(session: Session) -> None:
    assert load_options(session).max_length == 131_072
