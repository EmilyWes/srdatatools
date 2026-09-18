import pytest
from pydantic import ValidationError

from app.models.record import Affiliation, Author, PartialDate, Record


def test_record__empty_constructs_successfully() -> None:
    record = Record()
    assert record.title is None
    assert record.authors == []
    assert record.other_ids == {}


def test_record__full_valid_record_round_trips_all_fields() -> None:
    record = Record(
        title="A Study of Things",
        authors=[
            Author(
                family_name="Smith",
                given_name="Jane",
                orcid="0000-0001-2345-6789",
                other_ids={"scopus_author_id": "12345"},
                affiliations=[
                    Affiliation(name="University of Example", ror_id="01abc23de"),
                    Affiliation(name="Example Hospital"),
                ],
            )
        ],
        abstract="An abstract.",
        publication_date=PartialDate(year=2020, month=6, day=15),
        journal="Journal of Examples",
        volume="12",
        issue="3",
        pages="123-130",
        doi="10.1000/abc",
        pmid="12345678",
        issn="1234-5678",
        isbn="978-3-16-148410-0",
        other_ids={"eid": "2-s2.0-12345"},
        publication_type="journal article",
        keywords=["testing", "examples"],
        language="en",
        publisher="Example Press",
        url="https://example.com/paper",
        notes="Imported from a vendor's misc field.",
    )

    assert record.title == "A Study of Things"
    assert record.authors[0].family_name == "Smith"
    assert record.authors[0].orcid == "0000-0001-2345-6789"
    assert record.authors[0].other_ids == {"scopus_author_id": "12345"}
    assert record.authors[0].affiliations[0].ror_id == "01abc23de"
    assert record.publication_date == PartialDate(year=2020, month=6, day=15)
    assert record.other_ids == {"eid": "2-s2.0-12345"}
    assert record.keywords == ["testing", "examples"]


def test_author__full_name_fallback_for_unsplittable_name() -> None:
    author = Author(full_name="World Health Organization")
    assert author.family_name is None
    assert author.given_name is None
    assert author.full_name == "World Health Organization"


def test_author__multiple_affiliations() -> None:
    author = Author(
        family_name="Doe",
        affiliations=[
            Affiliation(name="University A"),
            Affiliation(name="University B", ror_id="02xyz34fg"),
        ],
    )
    assert len(author.affiliations) == 2
    assert author.affiliations[1].ror_id == "02xyz34fg"


@pytest.mark.parametrize(
    "raw_doi",
    [
        "https://doi.org/10.1000/ABC",
        "http://doi.org/10.1000/ABC",
        "doi:10.1000/ABC",
        "10.1000/abc",
        "  10.1000/ABC  ",
    ],
)
def test_record__doi_normalizes_to_same_canonical_value(raw_doi: str) -> None:
    record = Record(doi=raw_doi)
    assert record.doi == "10.1000/abc"


def test_record__doi_none_stays_none() -> None:
    record = Record(doi=None)
    assert record.doi is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"year": 2020},
        {"year": 2020, "month": 6},
        {"year": 2020, "month": 6, "day": 15},
    ],
)
def test_partial_date__valid_combinations_construct_successfully(
    kwargs: dict[str, int],
) -> None:
    PartialDate(**kwargs)


def test_partial_date__day_without_month_raises() -> None:
    with pytest.raises(ValidationError):
        PartialDate(day=15)


def test_partial_date__year_as_numeric_string_coerces_to_int() -> None:
    date = PartialDate(year="2020")  # type: ignore[arg-type]
    assert date.year == 2020


def test_partial_date__invalid_year_raises() -> None:
    with pytest.raises(ValidationError):
        PartialDate(year="not-a-year")  # type: ignore[arg-type]
