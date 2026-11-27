from typing import Literal, get_args

ScalarField = Literal[
    "title",
    "abstract",
    "journal",
    "conference_name",
    "volume",
    "issue",
    "doi",
    "pmid",
    "publication_type",
    "language",
    "publisher",
    "url",
    "notes",
]
SCALAR_FIELDS = frozenset(get_args(ScalarField))

DatePart = Literal["full", "year", "month", "day"]
DATE_PART_LABELS: dict[str, str] = {
    "full": "Full date",
    "year": "Year",
    "month": "Month",
    "day": "Day",
}

PagesBound = Literal["start", "end"]

FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "author_names": "Authors",
    "author_affiliations": "Affiliations",
    "abstract": "Abstract",
    "publication_date": "Publication date",
    "journal": "Journal",
    "conference_name": "Conference",
    "volume": "Volume",
    "issue": "Issue",
    "pages": "Pages",
    "doi": "DOI",
    "pmid": "PMID",
    "issn": "ISSN",
    "isbn": "ISBN",
    "other_ids": "Other IDs",
    "publication_type": "Publication type",
    "keywords": "Keywords",
    "language": "Language",
    "publisher": "Publisher",
    "url": "URL",
    "notes": "Notes",
}
