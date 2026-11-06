import datetime
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    ActivityLog,
    Base,
    Label,
    Record,
    RecordSource,
    SourceFile,
)
from app.db.queries import (
    count_filled_fields,
    count_keywords,
    count_label_values,
    count_publication_types,
    count_records,
    count_records_for_file,
    count_records_per_source_file,
    count_records_per_year,
    list_activity_log,
    list_keyword_prefixes,
    list_label_columns,
    list_record_labels,
    list_record_rows,
    list_record_sources,
    list_source_files,
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


def test_list_source_files__empty_when_none_imported(session: Session) -> None:
    assert list_source_files(session) == []


def test_list_source_files__returns_files_ordered_by_import_time(
    session: Session,
) -> None:
    newer = SourceFile(
        filename="scopus_export.csv",
        path=None,
        format="csv",
        imported_at=datetime.datetime(2026, 2, 1),
        row_count=10,
    )
    older = SourceFile(
        filename="pubmed_export.nbib",
        path=None,
        format="nbib",
        imported_at=datetime.datetime(2026, 1, 1),
        row_count=5,
    )
    session.add_all([newer, older])
    session.commit()

    result = list_source_files(session)

    assert [source_file.filename for source_file in result] == [
        "pubmed_export.nbib",
        "scopus_export.csv",
    ]


def test_list_activity_log__empty_when_nothing_logged(session: Session) -> None:
    assert list_activity_log(session) == []


def test_list_activity_log__returns_entries_oldest_first(session: Session) -> None:
    session.add_all(
        [
            ActivityLog(
                timestamp=datetime.datetime(2026, 2, 1),
                action_type="import",
                message="second",
            ),
            ActivityLog(
                timestamp=datetime.datetime(2026, 1, 1),
                action_type="import",
                message="first",
            ),
        ]
    )
    session.commit()

    result = list_activity_log(session)

    assert [entry.message for entry in result] == ["first", "second"]


def _source_file(
    filename: str, source: str | None, imported_at: datetime.datetime
) -> SourceFile:
    return SourceFile(
        filename=filename,
        path=None,
        format="ris",
        source=source,
        imported_at=imported_at,
        row_count=None,
    )


def _record(year: int | None, *source_files: SourceFile) -> Record:
    return Record(
        title="A title",
        publication_year=year,
        sources=[RecordSource(source_file=source_file) for source_file in source_files],
    )


@pytest.fixture
def library(session: Session) -> Session:
    pubmed = _source_file("pubmed.nbib", "pubmed", datetime.datetime(2026, 1, 1))
    scopus = _source_file("scopus.csv", "scopus", datetime.datetime(2026, 1, 2))
    unknown = _source_file("other.ris", None, datetime.datetime(2026, 1, 3))
    session.add_all(
        [
            _record(2020, pubmed),
            _record(2021, pubmed, scopus),
            _record(None, scopus),
            _record(2020, unknown),
        ]
    )
    session.commit()
    return session


def test_count_records__zero_when_empty(session: Session) -> None:
    assert count_records(session) == 0


def test_count_records__counts_all_records(library: Session) -> None:
    assert count_records(library) == 4


def test_count_records_for_file__counts_only_that_file(library: Session) -> None:
    pubmed = library.query(SourceFile).filter_by(filename="pubmed.nbib").one()

    assert count_records_for_file(library, pubmed.id) == 2


def test_count_records_per_year__ascending_with_unknown_last(
    library: Session,
) -> None:
    assert count_records_per_year(library) == [(2020, 2), (2021, 1), (None, 1)]


def test_list_record_rows__requested_fields_ordered_by_id(library: Session) -> None:
    rows = list_record_rows(library, ["publication_year"])

    assert rows == [
        {"id": 1, "publication_year": 2020},
        {"id": 2, "publication_year": 2021},
        {"id": 3, "publication_year": None},
        {"id": 4, "publication_year": 2020},
    ]


def test_list_record_sources__sources_per_record_in_import_order(
    library: Session,
) -> None:
    assert list_record_sources(library) == {
        1: ["pubmed"],
        2: ["pubmed", "scopus"],
        3: ["scopus"],
        4: [None],
    }


@pytest.fixture
def labeled(session: Session) -> Session:
    source_file = _source_file("asreview.csv", None, datetime.datetime(2026, 1, 1))
    first = Record(id=1)
    second = Record(id=2)

    def label(record: Record, phase: str, screener: str, value: str) -> Label:
        return Label(
            record=record,
            source_file=source_file,
            phase=phase,
            screener=screener,
            value=value,
        )

    session.add_all(
        [
            label(first, "tiab", "Emily", "include"),
            label(first, "ft", "screener 1", "exclude"),
            label(second, "tiab", "Emily", "exclude"),
            label(second, "tiab", "Emily", "maybe"),
            Record(id=3),
        ]
    )
    session.commit()
    return session


def test_list_label_columns__distinct_pairs_in_first_seen_order(
    labeled: Session,
) -> None:
    assert list_label_columns(labeled) == [("tiab", "Emily"), ("ft", "screener 1")]


def test_list_label_columns__empty_without_labels(session: Session) -> None:
    assert list_label_columns(session) == []


def test_list_record_labels__values_per_record_and_pair(labeled: Session) -> None:
    assert list_record_labels(labeled) == {
        1: {("tiab", "Emily"): ["include"], ("ft", "screener 1"): ["exclude"]},
        2: {("tiab", "Emily"): ["exclude", "maybe"]},
    }


def test_count_label_values__records_per_value_with_missing_as_unlabeled(
    labeled: Session,
) -> None:
    assert count_label_values(labeled) == {
        ("tiab", "Emily"): {"include": 1, "exclude": 1, "maybe": 1, "unlabeled": 1},
        ("ft", "screener 1"): {"exclude": 1, "unlabeled": 2},
    }


def test_count_label_values__empty_without_labels(session: Session) -> None:
    assert count_label_values(session) == {}


def test_count_filled_fields__counts_non_empty_values(session: Session) -> None:
    session.add_all(
        [
            Record(title="Paper", doi="10.1/a", authors=[{"full_name": "A"}]),
            Record(title="", keywords=["x"], authors=[]),
            Record(title="Other", other_ids={}),
        ]
    )
    session.commit()

    assert count_filled_fields(
        session, ["title", "doi", "authors", "keywords", "other_ids"]
    ) == [("title", 2), ("doi", 1), ("authors", 1), ("keywords", 1), ("other_ids", 0)]


@pytest.fixture
def keyworded(session: Session) -> Session:
    session.add_all(
        [
            Record(keywords=["Cancer", "[MeSH] Humans", "[MeSH] Mice", "cancer"]),
            Record(keywords=["cancer", "[MeSH] Humans", "Diet"]),
            Record(keywords=["[Author] diet", "Aging"]),
            Record(keywords=[]),
        ]
    )
    session.commit()
    return session


def test_count_keywords__per_prefix_case_insensitive_once_per_record(
    keyworded: Session,
) -> None:
    assert count_keywords(keyworded) == {
        None: [("Cancer", 2), ("Aging", 1), ("Diet", 1)],
        "MeSH": [("Humans", 2), ("Mice", 1)],
        "Author": [("diet", 1)],
    }


def test_list_keyword_prefixes__first_seen_order_without_unprefixed(
    keyworded: Session,
) -> None:
    assert list_keyword_prefixes(keyworded) == ["MeSH", "Author"]


def test_count_publication_types__case_insensitive_sorted_with_none(
    session: Session,
) -> None:
    session.add_all(
        [
            Record(publication_type="JOUR"),
            Record(publication_type="Book"),
            Record(publication_type="jour"),
            Record(publication_type=None),
            Record(publication_type=""),
            Record(publication_type="CONF"),
        ]
    )
    session.commit()

    assert count_publication_types(session) == [
        ("JOUR", 2),
        (None, 2),
        ("Book", 1),
        ("CONF", 1),
    ]


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
