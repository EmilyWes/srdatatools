import datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import Record, RecordSource, SourceFile
from app.db.record_source import (
    count_records_for_file,
    count_records_per_source_file,
    list_record_sources,
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


def test_count_records_for_file__counts_only_that_file(library: Session) -> None:
    pubmed = library.query(SourceFile).filter_by(filename="pubmed.nbib").one()

    assert count_records_for_file(library, pubmed.id) == 2


def test_list_record_sources__sources_per_record_in_import_order(
    library: Session,
) -> None:
    assert list_record_sources(library) == {
        1: ["pubmed"],
        2: ["pubmed", "scopus"],
        3: ["scopus"],
        4: [None],
    }


def test_list_record_sources__file_with_several_sources_lists_each(
    session: Session,
) -> None:
    source_file = _source_file("a.csv", None, datetime.datetime(2026, 1, 1))
    source_file.sources = ["pubmed", "asreview"]
    session.add(_record(None, source_file))
    session.commit()

    assert list(list_record_sources(session).values()) == [["pubmed", "asreview"]]


def test_count_records_per_source_file__shared_records_counted_separately(
    library: Session,
) -> None:
    assert count_records_per_source_file(library) == (
        [("pubmed.nbib", 1), ("scopus.csv", 1), ("other.ris", 1)],
        1,
    )


def test_count_records_per_source_file__sorted_by_count(session: Session) -> None:
    first = _source_file("first.ris", None, datetime.datetime(2026, 1, 1))
    second = _source_file("second.ris", None, datetime.datetime(2026, 1, 2))
    session.add_all([_record(None, first), _record(None, second)])
    session.add(_record(None, second))
    session.commit()

    assert count_records_per_source_file(session) == (
        [("second.ris", 2), ("first.ris", 1)],
        0,
    )


def test_count_records_per_source_file__empty_library(session: Session) -> None:
    assert count_records_per_source_file(session) == ([], 0)
