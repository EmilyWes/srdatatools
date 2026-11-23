from collections import Counter
from collections.abc import Iterator, Sequence

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Record, SourceFile
from app.db.store import store_parsed_rows
from app.gui.cleaning.options import CleaningOptions
from app.gui.cleaning.run import clean_records
from app.models.record import Label as LabelSchema
from app.models.record import Record as RecordSchema
from app.parsers.mapping import FieldMapping
from tests.mappings import mapping_of


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


def _store(
    session: Session,
    rows: Sequence[tuple[RecordSchema, dict[str, str]]],
    mapping: FieldMapping | None = None,
    use_first: Sequence[str] = (),
) -> SourceFile:
    source_file = store_parsed_rows(
        session, filename="x.csv", path=None, format="csv", parsed_rows=rows
    )
    source_file.field_mapping = (mapping or FieldMapping()).model_dump()
    source_file.quirk_choices = {"use_first": list(use_first)}
    session.commit()
    return source_file


def _titles(session: Session) -> list[str | None]:
    return [record.title for record in session.query(Record).order_by(Record.id)]


def test_clean_records__writes_back_and_counts_per_step(session: Session) -> None:
    _store(
        session,
        [
            (
                RecordSchema(title="A", pages="521-2"),
                {"Citation": "Nature. 2023 Aug;620(7974):589-594."},
            ),
            (RecordSchema(title="B", doi="10.1038/x [doi]"), {}),
            (RecordSchema(title="C"), {}),
        ],
    )

    total, changed, per_step = clean_records(session, CleaningOptions())
    session.commit()

    first, second, _ = session.query(Record).order_by(Record.id)
    assert (first.volume, first.issue, first.pages) == ("620", "7974", "521-522")
    assert second.doi == "10.1038/x"
    assert (total, changed) == (3, 2)
    assert list(per_step.items()) == [
        ("Strip DOI", 1),
        ("Values from Citation", 1),
        ("Pages set", 1),
    ]


def test_clean_records__only_the_given_ids(session: Session) -> None:
    _store(
        session,
        [(RecordSchema(pages="521-2"), {}), (RecordSchema(pages="521-2"), {})],
    )
    first_id = session.query(Record.id).order_by(Record.id).first()
    assert first_id is not None

    total, changed, _ = clean_records(session, CleaningOptions(), [first_id[0]])
    session.commit()

    assert (total, changed) == (1, 1)
    assert [r.pages for r in session.query(Record).order_by(Record.id)] == [
        "521-522",
        "521-2",
    ]


def test_clean_records__sniffs_the_author_separator_per_source_file(
    session: Session,
) -> None:
    _store(session, [(RecordSchema(author_names="Doe, J; Roe, K"), {})])
    _store(session, [(RecordSchema(author_names="Doe J and Roe K"), {})])

    clean_records(session, CleaningOptions())
    session.commit()

    assert [r.author_names for r in session.query(Record).order_by(Record.id)] == [
        "Doe, J|Roe, K",
        "Doe J|Roe K",
    ]


def test_clean_records__chosen_separator_is_used_for_every_file(
    session: Session,
) -> None:
    _store(session, [(RecordSchema(author_names="Romano M, Novacek MJ."), {})])

    clean_records(session, CleaningOptions(names_separator=","))
    session.commit()

    assert session.query(Record).one().author_names == "Romano M|Novacek MJ."


def test_clean_records__refills_from_the_source_mapping_and_ordering(
    session: Session,
) -> None:
    mapping = mapping_of({"TI": "title", "TT": "title", "OT": "title"})
    _store(
        session,
        [
            (
                RecordSchema(title="[Not Available]."),
                {"TI": "[Not Available].", "TT": "Translated", "OT": "Other"},
            )
        ],
        mapping,
        use_first=["OT"],
    )

    clean_records(session, CleaningOptions())
    session.commit()

    assert _titles(session) == ["Other"]


def test_clean_records__keeps_labels_and_cleans_date(session: Session) -> None:
    _store(
        session,
        [
            (
                RecordSchema(
                    pages="521-2",
                    publication_date="May 2001",
                    labels=[LabelSchema(phase="ft", screener="a", value="include")],
                ),
                {},
            )
        ],
    )

    clean_records(session, CleaningOptions())
    session.commit()

    record = session.query(Record).one()
    assert record.publication_date == "2001/05/"
    assert [label.value for label in record.labels] == ["include"]


def test_clean_records__unchanged_library_counts_nothing(session: Session) -> None:
    _store(session, [(RecordSchema(title="A", pages="1-2"), {})])

    assert clean_records(session, CleaningOptions()) == (1, 0, Counter())


def test_clean_records__empty_library(session: Session) -> None:
    assert clean_records(session, CleaningOptions()) == (0, 0, Counter())
