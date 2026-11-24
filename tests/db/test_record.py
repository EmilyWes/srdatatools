import datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import Label, Record, RecordSource, SourceFile
from app.db.record import (
    count_filled_fields,
    count_records,
    delete_records,
    list_record_rows,
    load_records,
    update_records,
)


def _source_file(
    filename: str, source: str | None, imported_at: datetime.datetime
) -> SourceFile:
    return SourceFile(
        filename=filename,
        path=None,
        format="ris",
        sources=[source] if source is not None else [],
        imported_at=imported_at,
        row_count=None,
    )


def _record(date: str | None, *source_files: SourceFile) -> Record:
    return Record(
        title="A title",
        publication_date=date,
        sources=[RecordSource(source_file=source_file) for source_file in source_files],
    )


@pytest.fixture
def library(session: Session) -> Session:
    pubmed = _source_file("pubmed.nbib", "pubmed", datetime.datetime(2026, 1, 1))
    scopus = _source_file("scopus.csv", "scopus", datetime.datetime(2026, 1, 2))
    unknown = _source_file("other.ris", None, datetime.datetime(2026, 1, 3))
    session.add_all(
        [
            _record("2020//", pubmed),
            _record("2021 Mar 4", pubmed, scopus),
            _record("n.d.", scopus),
            _record("2020/05/01", unknown),
        ]
    )
    session.commit()
    return session


def test_count_records__zero_when_empty(session: Session) -> None:
    assert count_records(session) == 0


def test_count_records__counts_all_records(library: Session) -> None:
    assert count_records(library) == 4


def test_list_record_rows__requested_fields_ordered_by_id(library: Session) -> None:
    rows = list_record_rows(library, ["publication_date"])

    assert rows == [
        {"id": 1, "publication_date": "2020//"},
        {"id": 2, "publication_date": "2021 Mar 4"},
        {"id": 3, "publication_date": "n.d."},
        {"id": 4, "publication_date": "2020/05/01"},
    ]


def test_count_filled_fields__counts_non_empty_values(session: Session) -> None:
    session.add_all(
        [
            Record(title="Paper", doi="10.1/a", author_names="A"),
            Record(title="", keywords=["x"], author_names=""),
            Record(title="Other", other_ids={}),
        ]
    )
    session.commit()

    assert count_filled_fields(
        session, ["title", "doi", "author_names", "keywords", "other_ids"]
    ) == [
        ("title", 2),
        ("doi", 1),
        ("author_names", 1),
        ("keywords", 1),
        ("other_ids", 0),
    ]


def _mapped_file(filename: str, source: str | None, mapped: list[str]) -> SourceFile:
    source_file = _source_file(filename, source, datetime.datetime(2026, 1, 1))
    source_file.field_mapping = {"rows": {key: {"target": "title"} for key in mapped}}
    return source_file


def test_load_records__all_by_id_with_sources_and_labels(session: Session) -> None:
    pubmed = _mapped_file("pubmed.nbib", "pubmed", ["TI"])
    session.add_all(
        [
            Record(id=2, title="B"),
            Record(
                id=1,
                title="A",
                sources=[RecordSource(source_file=pubmed, raw_fields={"TI": "A"})],
                labels=[
                    Label(
                        source_file=pubmed, phase="ft", screener="s1", value="exclude"
                    )
                ],
            ),
        ]
    )
    session.commit()
    session.expunge_all()

    first, second = load_records(session)
    session.close()

    assert (first.title, second.title) == ("A", "B")
    assert [s.source_file.filename for s in first.sources] == ["pubmed.nbib"]
    assert [label.value for label in first.labels] == ["exclude"]


def test_load_records__only_the_given_ids(session: Session) -> None:
    session.add_all([Record(id=1, title="A"), Record(id=2, title="B")])
    session.commit()

    assert [r.title for r in load_records(session, [2])] == ["B"]


def _label(record: Record, source_file: SourceFile, phase: str) -> Label:
    return Label(
        record=record,
        source_file=source_file,
        phase=phase,
        screener="screener 1",
        value="include",
    )


def test_delete_records__removes_records_their_sources_and_labels(
    session: Session,
) -> None:
    source_file = _source_file("export.ris", None, datetime.datetime(2026, 1, 1))
    first, second, kept = (
        Record(title=title, sources=[RecordSource(source_file=source_file)])
        for title in ("First", "Second", "Kept")
    )
    session.add_all([first, second, kept, _label(first, source_file, "ft")])
    session.commit()

    deleted = delete_records(session, {first.id, second.id})
    session.commit()

    assert deleted == 2
    assert [r.title for r in session.query(Record)] == ["Kept"]
    assert session.query(RecordSource).count() == 1
    assert session.query(Label).count() == 0
    assert [f.filename for f in session.query(SourceFile)] == ["export.ris"]


def test_update_records__sets_the_given_fields_only(session: Session) -> None:
    first = Record(title="First", doi="10.1/a")
    second = Record(title="Second")
    session.add_all([first, second])
    session.commit()

    update_records(session, {first.id: {"title": "Changed", "pages": "1-2"}})
    session.commit()

    assert [
        (r.title, r.doi, r.pages) for r in session.query(Record).order_by(Record.id)
    ] == [
        ("Changed", "10.1/a", "1-2"),
        ("Second", None, None),
    ]
