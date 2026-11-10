from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.db.settings import set_setting
from app.export.options import ExportOptions, load_options, reset_options, save_options


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
