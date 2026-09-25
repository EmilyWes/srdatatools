import datetime
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Author, Record, RecordAuthor, RecordSource, SourceFile
from app.models.record import Author as AuthorSchema
from app.models.record import Record as RecordSchema


class _AuthorResolver:
    """Resolves parsed authors to Author rows, reusing rows by ORCID.

    Record-level dedup hasn't run yet, so this is the only place duplicate
    Author rows are avoided; without it, importing the same ORCID twice would
    violate the unique constraint on Author.orcid.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._by_orcid: dict[str, Author] = {}

    def resolve(self, schema: AuthorSchema) -> Author:
        if schema.orcid is None:
            return Author(
                family_name=schema.family_name,
                given_name=schema.given_name,
                full_name=schema.full_name,
                other_ids=dict(schema.other_ids),
            )

        existing = self._by_orcid.get(schema.orcid)
        if existing is None:
            existing = self._session.scalars(
                select(Author).where(Author.orcid == schema.orcid)
            ).first()

        if existing is None:
            existing = Author(
                family_name=schema.family_name,
                given_name=schema.given_name,
                full_name=schema.full_name,
                orcid=schema.orcid,
                other_ids=dict(schema.other_ids),
            )
        else:
            existing.family_name = existing.family_name or schema.family_name
            existing.given_name = existing.given_name or schema.given_name
            existing.full_name = existing.full_name or schema.full_name
            existing.other_ids = {**schema.other_ids, **existing.other_ids}

        self._by_orcid[schema.orcid] = existing
        return existing


def _build_record_authors(
    schema: RecordSchema, resolver: _AuthorResolver
) -> list[RecordAuthor]:
    return [
        RecordAuthor(
            author=resolver.resolve(author),
            author_order=order,
            affiliations=[
                {"name": affiliation.name, "ror_id": affiliation.ror_id}
                for affiliation in author.affiliations
            ],
        )
        for order, author in enumerate(schema.authors)
    ]


def _build_record(schema: RecordSchema) -> Record:
    publication_year = None
    publication_month = None
    publication_day = None
    if schema.publication_date is not None:
        publication_year = schema.publication_date.year
        publication_month = schema.publication_date.month
        publication_day = schema.publication_date.day

    return Record(
        title=schema.title,
        abstract=schema.abstract,
        publication_year=publication_year,
        publication_month=publication_month,
        publication_day=publication_day,
        journal=schema.journal,
        conference_name=schema.conference_name,
        volume=schema.volume,
        issue=schema.issue,
        pages=schema.pages,
        doi=schema.doi,
        pmid=schema.pmid,
        issn=schema.issn,
        isbn=schema.isbn,
        other_ids=dict(schema.other_ids),
        publication_type=schema.publication_type,
        keywords=list(schema.keywords),
        language=schema.language,
        publisher=schema.publisher,
        url=schema.url,
        notes=schema.notes,
    )


def store_parsed_rows(
    session: Session,
    *,
    filename: str,
    path: str | None,
    format: str,
    parsed_rows: Sequence[tuple[RecordSchema, dict[str, str]]],
    imported_at: datetime.datetime | None = None,
) -> SourceFile:
    resolved_imported_at = imported_at or datetime.datetime.now()

    source_file = SourceFile(
        filename=filename,
        path=path,
        format=format,
        imported_at=resolved_imported_at,
        row_count=len(parsed_rows),
    )

    resolver = _AuthorResolver(session)
    for schema, raw_fields in parsed_rows:
        record = _build_record(schema)
        record.record_authors = _build_record_authors(schema, resolver)
        record.sources = [
            RecordSource(
                source_file=source_file,
                raw_fields=raw_fields,
                imported_at=resolved_imported_at,
            )
        ]
        session.add(record)

    session.add(source_file)
    return source_file
