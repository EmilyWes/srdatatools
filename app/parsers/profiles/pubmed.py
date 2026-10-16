import re

from app.models.record import Record
from app.parsers.profiles.base import FormatProfile, Profile

_NOT_AVAILABLE_TITLE = "[Not Available]."
_TRANSLATED_TITLE_TAG = "TT"
_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")


def expand_page_range(pages: str) -> str:
    """PubMed drops the leading digits the end page shares with the start: 521-2."""
    match = _PAGE_RANGE.match(pages)
    if match is None or len(match["end"]) >= len(match["start"]):
        return pages
    start, end = match["start"], match["end"]
    return f"{start}-{start[: -len(end)]}{end}"


def _first_line(value: str | None) -> str | None:
    return value.splitlines()[0] if value else value


def _fix_nbib_record(raw_fields: dict[str, str], record: Record) -> Record:
    title = record.title
    if title == _NOT_AVAILABLE_TITLE:
        title = raw_fields.get(_TRANSLATED_TITLE_TAG, "").strip() or None
    return record.model_copy(
        update={
            "title": title,
            "pages": expand_page_range(record.pages) if record.pages else None,
            "publication_type": _first_line(record.publication_type),
            "isbn": _first_line(record.isbn),
        }
    )


PUBMED = Profile(
    key="pubmed",
    label="PubMed",
    formats={
        "nbib": FormatProfile(aliases={"journal": ["jt"]}, fix_record=_fix_nbib_record),
    },
)
