import datetime
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    ActivityLog,
    AppSetting,
    Base,
    Label,
    Record,
    RecordSource,
    SourceFile,
)
from app.db.store import delete_library, remove_source_file, store_parsed_rows
from app.models.record import Affiliation, Author, PartialDate
from app.models.record import Label as LabelSchema
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


def test_store_parsed_rows__stores_source(session: Session) -> None:
    store_parsed_rows(
        session,
        filename="pubmed_export.nbib",
        path=None,
        format="nbib",
        source="pubmed",
        parsed_rows=[],
    )
    session.commit()

    assert session.query(SourceFile).one().source == "pubmed"


def test_store_parsed_rows__source_defaults_to_none(session: Session) -> None:
    store_parsed_rows(
        session, filename="export.ris", path=None, format="ris", parsed_rows=[]
    )
    session.commit()

    assert session.query(SourceFile).one().source is None


def test_store_parsed_rows__stores_sheet(session: Session) -> None:
    store_parsed_rows(
        session,
        filename="export.xlsx",
        path=None,
        format="excel",
        sheet="Records",
        parsed_rows=[],
    )
    session.commit()

    assert session.query(SourceFile).one().sheet == "Records"


def test_store_parsed_rows__sheet_defaults_to_none(session: Session) -> None:
    store_parsed_rows(
        session, filename="export.ris", path=None, format="ris", parsed_rows=[]
    )
    session.commit()

    assert session.query(SourceFile).one().sheet is None


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


def test_store_parsed_rows__stores_labels_linked_to_record_and_file(
    session: Session,
) -> None:
    labels = [
        LabelSchema(phase="tiab", screener="Emily", value="include"),
        LabelSchema(phase="ft", screener="screener 1", value="unlabeled"),
    ]

    store_parsed_rows(
        session,
        filename="asreview.csv",
        path=None,
        format="csv",
        parsed_rows=[(RecordSchema(title="Paper", labels=labels), {})],
    )
    session.commit()

    record = session.query(Record).one()
    source_file = session.query(SourceFile).one()
    assert [(lab.phase, lab.screener, lab.value) for lab in record.labels] == [
        ("tiab", "Emily", "include"),
        ("ft", "screener 1", "unlabeled"),
    ]
    assert all(lab.source_file is source_file for lab in record.labels)


def _source_file(filename: str) -> SourceFile:
    return SourceFile(
        filename=filename,
        path=None,
        format="ris",
        imported_at=datetime.datetime(2026, 1, 1),
        row_count=None,
    )


def _record(title: str, *source_files: SourceFile) -> Record:
    return Record(
        title=title,
        sources=[RecordSource(source_file=source_file) for source_file in source_files],
    )


def test_remove_source_file__removes_file_its_sources_and_records(
    session: Session,
) -> None:
    source_file = _source_file("export.ris")
    session.add_all([_record("First", source_file), _record("Second", source_file)])
    session.commit()

    removed = remove_source_file(session, source_file)
    session.commit()

    assert removed == 2
    assert session.query(SourceFile).count() == 0
    assert session.query(RecordSource).count() == 0
    assert session.query(Record).count() == 0


def test_remove_source_file__keeps_record_with_another_source(
    session: Session,
) -> None:
    removed_file = _source_file("removed.ris")
    kept_file = _source_file("kept.ris")
    session.add(_record("Shared", removed_file, kept_file))
    session.commit()

    removed = remove_source_file(session, removed_file)
    session.commit()

    assert removed == 0
    record = session.query(Record).one()
    assert [source.source_file.filename for source in record.sources] == ["kept.ris"]


def _label(record: Record, source_file: SourceFile, phase: str) -> Label:
    return Label(
        record=record,
        source_file=source_file,
        phase=phase,
        screener="screener 1",
        value="include",
    )


def test_remove_source_file__removes_its_labels(session: Session) -> None:
    source_file = _source_file("export.ris")
    record = _record("First", source_file)
    session.add_all([record, _label(record, source_file, "ft")])
    session.commit()

    remove_source_file(session, source_file)
    session.commit()

    assert session.query(Label).count() == 0


def test_remove_source_file__keeps_other_files_labels_on_shared_record(
    session: Session,
) -> None:
    removed_file = _source_file("removed.ris")
    kept_file = _source_file("kept.ris")
    record = _record("Shared", removed_file, kept_file)
    session.add_all(
        [record, _label(record, removed_file, "tiab"), _label(record, kept_file, "ft")]
    )
    session.commit()

    remove_source_file(session, removed_file)
    session.commit()

    assert [lab.phase for lab in session.query(Label)] == ["ft"]


def test_remove_source_file__leaves_other_files_untouched(session: Session) -> None:
    removed_file = _source_file("removed.ris")
    kept_file = _source_file("kept.ris")
    session.add_all([_record("Removed", removed_file), _record("Kept", kept_file)])
    session.commit()

    remove_source_file(session, removed_file)
    session.commit()

    assert [f.filename for f in session.query(SourceFile)] == ["kept.ris"]
    assert [r.title for r in session.query(Record)] == ["Kept"]


def test_delete_library__removes_all_files_sources_and_records(
    session: Session,
) -> None:
    first_file = _source_file("first.ris")
    second_file = _source_file("second.ris")
    session.add_all(
        [
            _record("First", first_file),
            _record("Shared", first_file, second_file),
            _record("Second", second_file),
        ]
    )
    session.commit()

    removed = delete_library(session)
    session.commit()

    assert removed == (2, 3)
    assert session.query(SourceFile).count() == 0
    assert session.query(RecordSource).count() == 0
    assert session.query(Record).count() == 0


def test_delete_library__removes_all_labels(session: Session) -> None:
    source_file = _source_file("first.ris")
    record = _record("First", source_file)
    session.add_all([record, _label(record, source_file, "ft")])
    session.commit()

    delete_library(session)
    session.commit()

    assert session.query(Label).count() == 0


def test_delete_library__keeps_activity_log_and_settings(session: Session) -> None:
    session.add_all(
        [
            _record("First", _source_file("first.ris")),
            ActivityLog(
                timestamp=datetime.datetime(2026, 1, 1),
                action_type="import",
                message="Imported",
            ),
            AppSetting(key="table_columns", value="[]"),
        ]
    )
    session.commit()

    delete_library(session)
    session.commit()

    assert session.query(ActivityLog).count() == 1
    assert session.query(AppSetting).count() == 1


def test_delete_library__empty_library_returns_zeros(session: Session) -> None:
    assert delete_library(session) == (0, 0)
