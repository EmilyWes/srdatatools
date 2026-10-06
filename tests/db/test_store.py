import datetime
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Record, SourceFile
from app.db.store import store_parsed_rows
from app.models.record import Affiliation, Author, PartialDate
from app.models.record import Record as RecordSchema


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


def test_store_parsed_rows__creates_source_file_with_row_count(
    session: Session,
) -> None:
    parsed_rows = [
        (RecordSchema(title="First"), {"TI": "First"}),
        (RecordSchema(title="Second"), {"TI": "Second"}),
    ]

    store_parsed_rows(
        session,
        filename="pubmed_export.nbib",
        path="/imports/pubmed_export.nbib",
        format="nbib",
        parsed_rows=parsed_rows,
        imported_at=datetime.datetime(2026, 1, 1),
    )
    session.commit()

    source_file = session.query(SourceFile).one()
    assert source_file.filename == "pubmed_export.nbib"
    assert source_file.format == "nbib"
    assert source_file.row_count == 2
    assert source_file.imported_at == datetime.datetime(2026, 1, 1)


def test_store_parsed_rows__creates_record_with_mapped_scalar_fields(
    session: Session,
) -> None:
    schema = RecordSchema(
        title="A Study of Things",
        doi="10.1000/abc",
        journal="Nature",
        abstract="An abstract.",
    )

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(schema, {"TI": "A Study of Things"})],
    )
    session.commit()

    record = session.query(Record).one()
    assert record.title == "A Study of Things"
    assert record.doi == "10.1000/abc"
    assert record.journal == "Nature"
    assert record.abstract == "An abstract."


def test_store_parsed_rows__preserves_raw_fields_on_record_source(
    session: Session,
) -> None:
    raw_fields = {"TI": "A Study of Things", "AB": "An abstract."}

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(RecordSchema(title="A Study of Things"), raw_fields)],
    )
    session.commit()

    record = session.query(Record).one()
    assert len(record.sources) == 1
    source = record.sources[0]
    assert source.raw_fields == raw_fields
    assert source.source_file.filename == "scopus_export.csv"


def test_store_parsed_rows__maps_publication_date_to_year_month_day(
    session: Session,
) -> None:
    schema = RecordSchema(
        title="Dated Paper",
        publication_date=PartialDate(year=2024, month=3, day=15),
    )

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(schema, {})],
    )
    session.commit()

    record = session.query(Record).one()
    assert record.publication_year == 2024
    assert record.publication_month == 3
    assert record.publication_day == 15


def test_store_parsed_rows__handles_multiple_rows_in_one_call(
    session: Session,
) -> None:
    parsed_rows = [
        (RecordSchema(title="First"), {"TI": "First"}),
        (RecordSchema(title="Second"), {"TI": "Second"}),
        (RecordSchema(title="Third"), {"TI": "Third"}),
    ]

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=parsed_rows,
    )
    session.commit()

    records = session.query(Record).order_by(Record.title).all()
    assert [record.title for record in records] == ["First", "Second", "Third"]


def test_store_parsed_rows__no_authors_is_empty_list(session: Session) -> None:
    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(RecordSchema(title="No Authors"), {})],
    )
    session.commit()

    assert session.query(Record).one().authors == []


def test_store_parsed_rows__stores_authors_in_order_as_full_dumps(
    session: Session,
) -> None:
    jane = Author(
        full_name="Jane Smith",
        orcid="0000-0001-2345-6789",
        affiliations=[Affiliation(name="University of Example")],
    )
    john = Author(full_name="John Doe")
    schema = RecordSchema(title="A Study of Things", authors=[jane, john])

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(schema, {})],
    )
    session.commit()

    record = session.query(Record).one()
    assert record.authors == [jane.model_dump(), john.model_dump()]
    assert [Author.model_validate(entry) for entry in record.authors] == [jane, john]


def test_store_parsed_rows__same_orcid_on_two_records_is_stored_on_each(
    session: Session,
) -> None:
    author = Author(full_name="Jane Smith", orcid="0000-0001-2345-6789")
    first = RecordSchema(title="First Paper", authors=[author])
    second = RecordSchema(title="Second Paper", authors=[author])

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(first, {}), (second, {})],
    )
    session.commit()

    records = session.query(Record).order_by(Record.title).all()
    assert [r.authors[0]["orcid"] for r in records] == [author.orcid, author.orcid]


def test_store_parsed_rows__stores_skipped_rows_on_source_file(
    session: Session,
) -> None:
    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(RecordSchema(title="Kept"), {})],
        skipped_rows=[(3, "row is blank"), (7, "row has more fields")],
    )
    session.commit()

    source_file = session.query(SourceFile).one()
    assert source_file.row_count == 1
    assert source_file.skipped_rows == [
        {"row_number": 3, "reason": "row is blank"},
        {"row_number": 7, "reason": "row has more fields"},
    ]


def test_store_parsed_rows__no_skipped_rows_is_empty_list(session: Session) -> None:
    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(RecordSchema(title="Kept"), {})],
    )
    session.commit()

    assert session.query(SourceFile).one().skipped_rows == []
