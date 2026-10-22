from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.db.settings import delete_setting, get_setting, set_setting


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


def test_get_setting__none_when_unset(session: Session) -> None:
    assert get_setting(session, "table_columns") is None


def test_set_setting__stored_value_is_returned(session: Session) -> None:
    set_setting(session, "table_columns", '["doi"]')
    session.commit()

    assert get_setting(session, "table_columns") == '["doi"]'


def test_set_setting__overwrites_existing_value(session: Session) -> None:
    set_setting(session, "table_columns", '["doi"]')
    set_setting(session, "table_columns", '["title"]')
    session.commit()

    assert get_setting(session, "table_columns") == '["title"]'


def test_delete_setting__removes_value(session: Session) -> None:
    set_setting(session, "table_columns", '["doi"]')
    session.commit()

    delete_setting(session, "table_columns")
    session.commit()

    assert get_setting(session, "table_columns") is None


def test_delete_setting__no_op_when_unset(session: Session) -> None:
    delete_setting(session, "table_columns")

    assert get_setting(session, "table_columns") is None
