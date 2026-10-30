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
_CSV_KEYWORDS = "Keyword"
_CSV_CONCEPTS = "Concept"
_CSV_TOPICS = "Topic"
_CONCEPT_PREFIX = "[Concept] "
_TOPIC_PREFIX = "[Topic] "
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


def _csv_authors(raw_fields: dict[str, str]) -> list[Author]:
    names = _split(raw_fields.get(_CSV_AUTHORS))
    ids = _aligned(raw_fields, _CSV_AUTHOR_IDS, len(names))
    orcids = _aligned(raw_fields, _CSV_ORCIDS, len(names))
    authors = []
    for index, name in enumerate(names):
        author = Author(full_name=name)
        if ids and ids[index]:
            author.other_ids[_AUTHOR_ID_KEY] = ids[index]
        if orcids and orcids[index]:
            author.orcid = orcids[index].removeprefix(_ORCID_PREFIX)
        authors.append(author)
    return [author for author in authors if author.full_name]


def _csv_keywords(raw_fields: dict[str, str]) -> list[str]:
    def pieces(column: str, prefix: str = "") -> list[str]:
        return [prefix + kw for kw in _split(raw_fields.get(column)) if kw]

    return (
        pieces(_CSV_KEYWORDS)
        + pieces(_CSV_CONCEPTS, _CONCEPT_PREFIX)
        + pieces(_CSV_TOPICS, _TOPIC_PREFIX)
    )


def _fix_csv_record(
    raw_fields: dict[str, str], record: Record, mapping: FieldMapping
) -> Record:
    update: dict[str, object] = {}
    if record.authors:
        update["authors"] = _csv_authors(raw_fields)
    if record.keywords:
        update["keywords"] = _csv_keywords(raw_fields)
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
                "authors": ["author"],
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
                    "author ids",
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
                    "orcid",
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
