import csv
import re
from io import StringIO

from app.models.record import Record
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.base import FormatProfile, Profile

_NOT_AVAILABLE_TITLE = "[Not Available]."
_TRANSLATED_TITLE_TAG = "TT"
_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")

_ET_AL = "et al."

_NBIB_PMID_LINE = re.compile(r"^PMID ?- ", re.MULTILINE)
_NBIB_OWN_NLM_LINE = re.compile(r"^OWN ?- NLM\s*$", re.MULTILINE)
_CSV_HEADERS = {"pmid", "citation", "journal/book"}


def expand_page_range(pages: str) -> str:
    """PubMed drops the leading digits the end page shares with the start: 521-2."""
    match = _PAGE_RANGE.match(pages)
    if match is None or len(match["end"]) >= len(match["start"]):
        return pages
    start, end = match["start"], match["end"]
    return f"{start}-{start[: -len(end)]}{end}"


def _first_line(value: str | None) -> str | None:
    return value.splitlines()[0] if value else value


def _fix_nbib_record(
    raw_fields: dict[str, str], record: Record, mapping: FieldMapping
) -> Record:
    title = record.title
    if title == _NOT_AVAILABLE_TITLE:
        title = None
        if mapping.targets.get(_TRANSLATED_TITLE_TAG) == "title":
            title = raw_fields.get(_TRANSLATED_TITLE_TAG, "").strip() or None
    return record.model_copy(
        update={
            "title": title,
            "pages": expand_page_range(record.pages) if record.pages else None,
            "publication_type": _first_line(record.publication_type),
            "isbn": _first_line(record.isbn),
        }
    )


def _fix_csv_record(
    raw_fields: dict[str, str], record: Record, mapping: FieldMapping
) -> Record:
    authors = [author for author in record.authors if author.full_name != _ET_AL]
    if authors and authors[-1].full_name:
        last_name = authors[-1].full_name.rstrip(".")
        authors[-1] = authors[-1].model_copy(update={"full_name": last_name})
    return record.model_copy(update={"authors": authors})


def _matches_nbib(text: str) -> bool:
    return bool(_NBIB_PMID_LINE.search(text) and _NBIB_OWN_NLM_LINE.search(text))


def _matches_csv(text: str) -> bool:
    header = next(csv.reader(StringIO(text)), [])
    return _CSV_HEADERS <= {column.strip().lower() for column in header}


PUBMED = Profile(
    key="pubmed",
    label="PubMed",
    formats={
        "nbib": FormatProfile(
            aliases={"journal": ["jt", "bti"], "title": ["ti", "tt"]},
            fix_record=_fix_nbib_record,
            matches=_matches_nbib,
        ),
        "csv": FormatProfile(
            aliases={
                "journal": ["journal/book"],
                "other_ids.pmc": ["pmcid"],
                "other_ids.mid": ["nihms id"],
            },
            fix_record=_fix_csv_record,
            matches=_matches_csv,
            list_delimiter=",",
        ),
    },
)
