from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.cleaning.options import (
    CLEANING_BOXES,
    CleaningOptions,
    load_options,
    reset_options,
    save_options,
)
from app.db.models import Base
from app.db.settings import set_setting
from app.parsers.profiles.overview import QuirkItem


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
    assert load_options(session) == CleaningOptions()


def test_save_options__round_trips(session: Session) -> None:
    options = CleaningOptions(drop_trailing=True, empty_values=["n/a", "-"])

    save_options(session, options)
    session.commit()

    assert load_options(session) == options


def test_load_options__invalid_stored_value_falls_back_to_defaults(
    session: Session,
) -> None:
    set_setting(session, "cleaning_options", '{"pages_set": "maybe"}')

    assert load_options(session) == CleaningOptions()


def test_load_options__missing_keys_keep_the_defaults(session: Session) -> None:
    set_setting(session, "cleaning_options", '{"drop_trailing": true}')

    assert load_options(session) == CleaningOptions(drop_trailing=True)


def test_reset_options__goes_back_to_defaults(session: Session) -> None:
    save_options(session, CleaningOptions(pages_set=False))
    session.commit()

    reset_options(session)
    session.commit()

    assert load_options(session) == CleaningOptions()


def test_cleaning_boxes__every_control_key_is_an_option() -> None:
    keys = [item.key for box in CLEANING_BOXES for item in box.items]

    assert set(keys) <= set(CleaningOptions.model_fields)
    assert len(keys) == len(set(keys))


def test_cleaning_boxes__titles_in_order() -> None:
    assert [box.title for box in CLEANING_BOXES] == [
        "ISSN/ISBN",
        "Authors",
        "Empty values",
        "Identifiers",
        "Other",
        "From raw fields",
    ]


def test_cleaning_boxes__split_authors_enables_its_dependants() -> None:
    [authors] = [box for box in CLEANING_BOXES if box.title == "Authors"]

    enabled_by_split = [
        item.key
        for item in authors.items
        if isinstance(item, QuirkItem) and item.enabled_by == "split_authors"
    ]

    assert enabled_by_split == [
        "names_separator",
        "affiliations_separator",
        "ids_separator",
        "id_from_name",
        "author_strip_extras",
        "affiliation_start",
    ]
