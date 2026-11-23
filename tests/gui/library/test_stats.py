from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Record
from app.gui.library.stats import (
    count_data_quality,
    count_keywords,
    count_publication_types,
    count_records_per_year,
    list_author_id_keys,
    list_keyword_prefixes,
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


def test_count_records_per_year__ascending_with_unknown_last(
    session: Session,
) -> None:
    dates = ["2020//", "2021 Mar 4", "n.d.", "2020/05/01"]
    session.add_all([Record(publication_date=date) for date in dates])
    session.commit()

    assert count_records_per_year(session) == [(2020, 2), (2021, 1), (None, 1)]


def test_count_data_quality__unparsed_dates(session: Session) -> None:
    dates = ["2020/05/01", "1994//", "2020/05/", "2020 May", "14/05/2020", "/03/", None]
    session.add_all([Record(publication_date=date) for date in dates])
    session.commit()

    assert dict(count_data_quality(session))["Unparsed dates"] == 3


@pytest.mark.parametrize(
    ("names", "ids", "misaligned"),
    [
        ("A|B", "x:1|x:2", False),
        ("A|B", "x:1", True),
        ("A|B", "x:1|x:2|x:3", True),
        (None, "x:1", True),
        ("A|B", "x:[1;2]", True),
        ("A|B", None, False),
    ],
)
def test_count_data_quality__misaligned_authors(
    session: Session, names: str | None, ids: str | None, misaligned: bool
) -> None:
    session.add(Record(author_names=names, author_ids=ids))
    session.commit()

    assert dict(count_data_quality(session))["Misaligned authors"] == misaligned


def test_count_data_quality__rows_in_order(session: Session) -> None:
    assert count_data_quality(session) == [
        ("Unparsed dates", 0),
        ("Misaligned authors", 0),
        ("Unmapped pub. types", 0),
    ]


@pytest.mark.parametrize(
    ("publication_type", "unmapped"),
    [
        ("Journal article", False),
        ("JOUR", True),
        ("GEN", True),
        ("", False),
        (None, False),
    ],
)
def test_count_data_quality__unmapped_publication_types(
    session: Session, publication_type: str | None, unmapped: bool
) -> None:
    session.add(Record(publication_type=publication_type))
    session.commit()

    assert dict(count_data_quality(session))["Unmapped pub. types"] == unmapped


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


def test_count_keywords__unsplit_value_counts_as_one_keyword(
    session: Session,
) -> None:
    session.add(Record(keywords=["keywords:[Cancer; Diet]", "MeSH:[Humans]"]))
    session.commit()

    assert count_keywords(session) == {
        None: [("Cancer; Diet", 1)],
        "MeSH": [("Humans", 1)],
    }


def test_list_author_id_keys__first_seen_order_cleaned_and_unsplit(
    session: Session,
) -> None:
    session.add_all(
        [
            Record(author_ids="scopus_author_id:[1; 2]"),
            Record(author_ids="pmid:1|orcid:2"),
            Record(author_ids="orcid:[a], scopus_author_id:[3]"),
            Record(author_ids=None),
        ]
    )
    session.commit()

    assert list_author_id_keys(session) == ["scopus_author_id", "pmid", "orcid"]


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
