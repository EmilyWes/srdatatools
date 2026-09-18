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


class Affiliation(BaseModel):
    name: str | None = None
    ror_id: str | None = None


class Author(BaseModel):
    family_name: str | None = None
    given_name: str | None = None
    full_name: str | None = None
    orcid: str | None = None
    other_ids: dict[str, str] = Field(default_factory=dict)
    affiliations: list[Affiliation] = Field(default_factory=list)


class Record(BaseModel):
    title: str | None = None
    authors: list[Author] = Field(default_factory=list)
    abstract: str | None = None
    publication_date: PartialDate | None = None
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

    @field_validator("doi")
    @classmethod
    def normalize_doi(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if value.lower().startswith(prefix):
                value = value[len(prefix) :]
                break
        return value.lower()
