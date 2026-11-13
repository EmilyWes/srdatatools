import datetime
from collections import Counter
from collections.abc import Iterator, Sequence

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.cleaning.options import CleaningOptions
from app.db.models import (
    ActivityLog,
    AppSetting,
    Base,
    Label,
    Record,
    RecordSource,
    SourceFile,
)
from app.db.store import (
    clean_records,
    delete_library,
    delete_records,
    remove_source_file,
    store_parsed_rows,
)
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


def test_store_parsed_rows__stores_publication_date(session: Session) -> None:
    schema = RecordSchema(title="Dated Paper", publication_date="2024 Mar 15")

    store_parsed_rows(
        session,
        filename="scopus_export.csv",
        path=None,
        format="csv",
        parsed_rows=[(schema, {})],
    )
    session.commit()

    assert session.query(Record).one().publication_date == "2024 Mar 15"


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


def test_store_parsed_rows__stores_author_fields(session: Session) -> None:
    schema = RecordSchema(
        title="A Study of Things",
        author_names="Smith, Jane|Doe, John",
        author_ids="orcid:0000-0001-2345-6789|",
        author_affiliations="University of Example",
    )

    store_parsed_rows(
        session,
        filename="scopus_export.ris",
        path=None,
        format="ris",
        parsed_rows=[(schema, {})],
    )
    session.commit()

    record = session.query(Record).one()
    assert record.author_names == "Smith, Jane|Doe, John"
    assert record.author_ids == "orcid:0000-0001-2345-6789|"
    assert record.author_affiliations == "University of Example"


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


def test_delete_records__removes_records_their_sources_and_labels(
    session: Session,
) -> None:
    source_file = _source_file("export.ris")
    first = _record("First", source_file)
    second = _record("Second", source_file)
    kept = _record("Kept", source_file)
    session.add_all([first, second, kept, _label(first, source_file, "ft")])
    session.commit()

    deleted = delete_records(session, {first.id, second.id})
    session.commit()

    assert deleted == 2
    assert [r.title for r in session.query(Record)] == ["Kept"]
    assert session.query(RecordSource).count() == 1
    assert session.query(Label).count() == 0
    assert [f.filename for f in session.query(SourceFile)] == ["export.ris"]


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
