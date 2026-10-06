import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "record"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None]
    authors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    abstract: Mapped[str | None]
    publication_year: Mapped[int | None]
    publication_month: Mapped[int | None]
    publication_day: Mapped[int | None]
    journal: Mapped[str | None]
    conference_name: Mapped[str | None]
    volume: Mapped[str | None]
    issue: Mapped[str | None]
    pages: Mapped[str | None]
    doi: Mapped[str | None] = mapped_column(index=True)
    pmid: Mapped[str | None] = mapped_column(index=True)
    issn: Mapped[str | None]
    isbn: Mapped[str | None]
    other_ids: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    publication_type: Mapped[str | None]
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str | None]
    publisher: Mapped[str | None]
    url: Mapped[str | None]
    notes: Mapped[str | None]

    sources: Mapped[list["RecordSource"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class SourceFile(Base):
    __tablename__ = "source_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str]
    path: Mapped[str | None]
    format: Mapped[str]
    imported_at: Mapped[datetime.datetime]
    row_count: Mapped[int | None]
    skipped_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    record_sources: Mapped[list["RecordSource"]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )


class RecordSource(Base):
    __tablename__ = "record_source"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("record.id"), index=True)
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_file.id"), index=True
    )
    raw_fields: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    record: Mapped["Record"] = relationship(back_populates="sources")
    source_file: Mapped["SourceFile"] = relationship(back_populates="record_sources")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime.datetime]
    action_type: Mapped[str]
    message: Mapped[str]
    record_id: Mapped[int | None] = mapped_column(ForeignKey("record.id"), index=True)
