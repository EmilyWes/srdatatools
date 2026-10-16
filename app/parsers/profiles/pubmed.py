import re
from typing import Any

from app.models.record import Record
from app.parsers.mapping import parse_date_string
from app.parsers.profiles.base import FormatProfile, Profile

_NOT_AVAILABLE_TITLE = "[Not Available]."
_TRANSLATED_TITLE_TAG = "TT"
_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")

_CITATION_COLUMN = "Citation"
_ET_AL = "et al."
# "Nature. 2023 Aug;620(7974):589-594. doi: ..."; book and preprint citations have
# other layouts and don't match.
_JOURNAL_CITATION = re.compile(
    r"^.*?\. (?P<date>\d{4}[^;.]*);(?P<volume>[^(:]*)(?:\((?P<issue>[^)]*)\))?"
    r":(?P<pages>.+?)\.(?: |$)"
)


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


def _from_citation(citation: str, record: Record) -> dict[str, Any]:
    match = _JOURNAL_CITATION.match(citation)
    if match is None:
        return {}
    found = {
        "volume": (match["volume"] or "").strip(),
        "issue": (match["issue"] or "").strip(),
        "pages": expand_page_range(match["pages"].strip()),
    }
    update: dict[str, Any] = {
        name: value
        for name, value in found.items()
        if value and getattr(record, name) is None
    }
    date = record.publication_date
    cited = parse_date_string(match["date"])
    if cited is not None and (
        date is None or (date.year == cited.year and date.month is None)
    ):
        update["publication_date"] = cited
    return update


def _fix_csv_record(raw_fields: dict[str, str], record: Record) -> Record:
    authors = [author for author in record.authors if author.full_name != _ET_AL]
    if authors and authors[-1].full_name:
        last_name = authors[-1].full_name.rstrip(".")
        authors[-1] = authors[-1].model_copy(update={"full_name": last_name})
    citation = raw_fields.get(_CITATION_COLUMN) or ""
    return record.model_copy(
        update={"authors": authors, **_from_citation(citation, record)}
    )


PUBMED = Profile(
    key="pubmed",
    label="PubMed",
    formats={
        "nbib": FormatProfile(
            aliases={"journal": ["jt", "bti"]}, fix_record=_fix_nbib_record
        ),
        "csv": FormatProfile(
            aliases={
                "journal": ["journal/book"],
                "other_ids.pmc": ["pmcid"],
                "other_ids.mid": ["nihms id"],
            },
            fix_record=_fix_csv_record,
            list_delimiter=",",
        ),
    },
)
