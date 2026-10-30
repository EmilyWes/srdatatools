import csv
import logging
from io import StringIO

from app.models.record import Author, Record
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.base import FormatProfile, Profile

logger = logging.getLogger(__name__)

_LIST_DELIMITER = "|"
_AUTHOR_ID_KEY = "openalex_author_id"
_ORCID_PREFIX = "https://orcid.org/"
_PMID_PREFIX = "https://pubmed.ncbi.nlm.nih.gov/"

_CSV_AUTHORS = "Author"
_CSV_AUTHOR_IDS = "Author IDs"
_CSV_ORCIDS = "ORCID"
# The first mapped, non-empty one sets the author count; the others are zipped onto it.
_CSV_AUTHOR_COLUMNS = (_CSV_AUTHORS, _CSV_ORCIDS, _CSV_AUTHOR_IDS)
_CSV_KEYWORD_PREFIXES = {"Keyword": "", "Concept": "[Concept] ", "Topic": "[Topic] "}
_CSV_MARKER_HEADERS = frozenset({"work id", "concept ids"})


def _split(value: str | None) -> list[str]:
    """Keeps empty pieces: ORCID has an empty slot for each author without one."""
    if not value or not value.strip():
        return []
    return [piece.strip() for piece in value.split(_LIST_DELIMITER)]


def _aligned(raw_fields: dict[str, str], column: str, count: int) -> list[str]:
    values = _split(raw_fields.get(column))
    if values and len(values) != count:
        logger.warning(
            "OpenAlex %r has %d entries for %d authors; ignoring it",
            column,
            len(values),
            count,
        )
        return []
    return values


def _csv_authors(raw_fields: dict[str, str], columns: list[str]) -> list[Author]:
    count = next(
        (len(values) for c in columns if (values := _split(raw_fields.get(c)))), 0
    )
    aligned = {c: _aligned(raw_fields, c, count) for c in columns}
    names, orcids, ids = (aligned.get(c) or [""] * count for c in _CSV_AUTHOR_COLUMNS)
    authors = []
    for name, orcid, author_id in zip(names, orcids, ids, strict=True):
        author = Author(
            full_name=name or None,
            orcid=orcid.removeprefix(_ORCID_PREFIX) or None,
            other_ids={_AUTHOR_ID_KEY: author_id} if author_id else {},
        )
        if author.full_name or author.orcid or author.other_ids:
            authors.append(author)
    return authors


def _csv_keywords(raw_fields: dict[str, str], columns: list[str]) -> list[str]:
    return [
        _CSV_KEYWORD_PREFIXES[column] + keyword
        for column in columns
        for keyword in _split(raw_fields.get(column))
        if keyword
    ]


def _fix_csv_record(
    raw_fields: dict[str, str], record: Record, mapping: FieldMapping
) -> Record:
    update: dict[str, object] = {}
    mapped_authors = mapping.keys_for("authors")
    author_columns = [c for c in _CSV_AUTHOR_COLUMNS if c in mapped_authors]
    if author_columns:
        update["authors"] = _csv_authors(raw_fields, author_columns)
    mapped_keywords = mapping.keys_for("keywords")
    keyword_columns = [c for c in _CSV_KEYWORD_PREFIXES if c in mapped_keywords]
    if keyword_columns:
        update["keywords"] = _csv_keywords(raw_fields, keyword_columns)
    if record.issn:
        update["issn"] = record.issn.split(_LIST_DELIMITER)[0].strip()
    if record.pmid:
        update["pmid"] = record.pmid.removeprefix(_PMID_PREFIX)
    return record.model_copy(update=update)


def _matches_csv(text: str) -> bool:
    header = next(csv.reader(StringIO(text)), [])
    return _CSV_MARKER_HEADERS <= {column.strip().lower() for column in header}


def _unchanged(
    raw_fields: dict[str, str], record: Record, mapping: FieldMapping
) -> Record:
    return record


def _never(text: str) -> bool:
    """OpenAlex RIS and BibTeX exports carry nothing that marks them as OpenAlex."""
    return False


OPENALEX = Profile(
    key="openalex",
    label="OpenAlex",
    formats={
        "csv": FormatProfile(
            aliases={
                "authors": ["author", "orcid", "author ids"],
                "journal": ["source"],
                "keywords": ["keyword", "concept", "topic"],
                "publication_type": ["type"],
                "other_ids.openalex": ["work id"],
            },
            fix_record=_fix_csv_record,
            matches=_matches_csv,
            list_delimiter=_LIST_DELIMITER,
            ignored_keys=frozenset(
                {
                    "concept ids",
                    "keyword ids",
                    "topic ids",
                    "source ids",
                    "volume ids",
                    "oa source",
                    "source ojs",
                    "oa published",
                    "has orcid",
                    "has pmcid",
                    "has abstract",
                    "pubmed",
                    "ror id",
                }
            ),
        ),
        "ris": FormatProfile(
            aliases={"authors": ["au", "c1"]},
            fix_record=_unchanged,
            matches=_never,
        ),
        "bibtex": FormatProfile(
            aliases={},
            fix_record=_unchanged,
            matches=_never,
            list_delimiter=",",
        ),
    },
)
