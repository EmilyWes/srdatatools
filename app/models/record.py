import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PartialDate(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None

    @model_validator(mode="after")
    def day_requires_month(self) -> "PartialDate":
        if self.day is not None and self.month is None:
            raise ValueError("day requires month to also be set")
        return self


_LEADING_YEAR = re.compile(r"\d{4}")


def publication_year(date: str | None) -> int | None:
    """The year a date string starts with, if it starts with four digits."""
    match = _LEADING_YEAR.match(date or "")
    return int(match[0]) if match else None


LabelValue = Literal["include", "exclude", "maybe", "unknown", "unlabeled"]


class Label(BaseModel):
    phase: str
    screener: str
    value: LabelValue


class Record(BaseModel):
    title: str | None = None
    author_names: str | None = None
    # One slot per author, "key:value" ids; see app.parsers.authors.
    author_ids: str | None = None
    author_affiliations: str | None = None
    abstract: str | None = None
    # Cleaned to YYYY/MM/DD, unknown parts left empty: 1994//.
    publication_date: str | None = None
    journal: str | None = None
    conference_name: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    pmid: str | None = None
    issn: str | None = None
    isbn: str | None = None
    other_ids: dict[str, str] = Field(default_factory=dict)
    publication_type: str | None = None
    keywords: list[str] = Field(default_factory=list)
    language: str | None = None
    publisher: str | None = None
    url: str | None = None
    notes: str | None = None
    labels: list[Label] = Field(default_factory=list)

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if value.lower().startswith(prefix):
                value = value[len(prefix) :].strip()
                break
        return value.lower()
