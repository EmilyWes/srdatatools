import csv
import logging
import re
from io import StringIO

from app.models.record import Affiliation, Author, Record
from app.parsers.authors import author_from_name
from app.parsers.profiles.base import FormatProfile, Profile

logger = logging.getLogger(__name__)

_AUTHOR_KEYWORD_PREFIX = "[Author] "
_LIST_DELIMITER = ";"
_NAME_SEPARATOR = ","
_AFFILIATION_SEPARATOR = ", "
_AUTHOR_ID_KEY = "scopus_author_id"

_CSV_FULL_NAMES = "Author full names"
_CSV_ABBREVIATED_NAMES = "Authors"
_CSV_AUTHOR_IDS = "Author(s) ID"
_CSV_AUTHORS_WITH_AFFILIATIONS = "Authors with affiliations"
_CSV_AUTHOR_KEYWORDS = "Author Keywords"
_CSV_INDEX_KEYWORDS = "Index Keywords"
_CSV_EID_HEADER = "eid"

_RIS_NOTES_TAG = "N1"
_RIS_EID_NOTE = "EID: "
_RIS_CONFERENCE_NOTE = "Conference name: "
_RIS_DB_LINE = re.compile(r"^DB  - Scopus\s*$", re.MULTILINE)

# "Teng, Yu (60652739200)": the Scopus author id is appended to each full name.
_NAME_WITH_ID = re.compile(r"^(?P<name>.*?)\s*\((?P<id>\d+)\)$")


def _split(value: str | None) -> list[str]:
    """Keeps empty pieces so positions line up across the parallel author columns."""
    if not value or not value.strip():
        return []
    return [piece.strip() for piece in value.split(_LIST_DELIMITER)]


def _aligned(column: str, values: list[str], count: int) -> list[str]:
    if values and len(values) != count:
        logger.warning(
            "Scopus %r has %d entries for %d authors; ignoring it",
            column,
            len(values),
            count,
        )
        return []
    return values


def _base_authors(raw_fields: dict[str, str]) -> tuple[list[Author], list[str]]:
    full_names = _split(raw_fields.get(_CSV_FULL_NAMES))
    if not full_names:
        names = _split(raw_fields.get(_CSV_ABBREVIATED_NAMES))
        return [Author(full_name=name) for name in names], [""] * len(names)
    authors, ids = [], []
    for entry in full_names:
        match = _NAME_WITH_ID.match(entry)
        name = match["name"] if match else entry
        ids.append(match["id"] if match else "")
        authors.append(author_from_name(name, _NAME_SEPARATOR))
    return authors, ids


def _scopus_csv_authors(raw_fields: dict[str, str]) -> list[Author]:
    authors, embedded_ids = _base_authors(raw_fields)
    count = len(authors)
    column_ids = _aligned(
        _CSV_AUTHOR_IDS, _split(raw_fields.get(_CSV_AUTHOR_IDS)), count
    )
    with_affiliations = _aligned(
        _CSV_AUTHORS_WITH_AFFILIATIONS,
        _split(raw_fields.get(_CSV_AUTHORS_WITH_AFFILIATIONS)),
        count,
    )
    fixed = []
    for index, author in enumerate(authors):
        update: dict[str, object] = {}
        author_id = embedded_ids[index] or (column_ids[index] if column_ids else "")
        if author_id:
            update["other_ids"] = {_AUTHOR_ID_KEY: author_id}
        if with_affiliations:
            # "Teng Y., Guangxi Cartier Technology Ltd., ...": drop the leading name.
            _, _, affiliation = with_affiliations[index].partition(
                _AFFILIATION_SEPARATOR
            )
            if affiliation:
                update["affiliations"] = [Affiliation(name=affiliation)]
        fixed.append(author.model_copy(update=update))
    return fixed


def _scopus_csv_keywords(raw_fields: dict[str, str]) -> list[str]:
    author_keywords = _split(raw_fields.get(_CSV_AUTHOR_KEYWORDS))
    index_keywords = _split(raw_fields.get(_CSV_INDEX_KEYWORDS))
    return [_AUTHOR_KEYWORD_PREFIX + kw for kw in author_keywords if kw] + [
        kw for kw in index_keywords if kw
    ]


def _fix_csv_record(raw_fields: dict[str, str], record: Record) -> Record:
    update: dict[str, object] = {}
    if record.authors:
        update["authors"] = _scopus_csv_authors(raw_fields)
    if record.keywords:
        update["keywords"] = _scopus_csv_keywords(raw_fields)
    return record.model_copy(update=update)


def _matches_csv(text: str) -> bool:
    header = next(csv.reader(StringIO(text)), [])
    return _CSV_EID_HEADER in {column.strip().lower() for column in header}


def _ris_note(raw_fields: dict[str, str], prefix: str) -> str | None:
    """Scopus packs labelled values into N1 lines, e.g. "EID: 2-s2.0-105040180364"."""
    for line in raw_fields.get(_RIS_NOTES_TAG, "").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip() or None
    return None


def _fix_ris_record(raw_fields: dict[str, str], record: Record) -> Record:
    update: dict[str, object] = {}
    eid = _ris_note(raw_fields, _RIS_EID_NOTE)
    if eid is not None:
        update["other_ids"] = {**record.other_ids, "eid": eid}
    if record.conference_name is None:
        update["conference_name"] = _ris_note(raw_fields, _RIS_CONFERENCE_NOTE)
    return record.model_copy(update=update)


def _matches_ris(text: str) -> bool:
    return bool(_RIS_DB_LINE.search(text))


SCOPUS = Profile(
    key="scopus",
    label="Scopus",
    formats={
        "csv": FormatProfile(
            aliases={
                "authors": [
                    "author full names",
                    "authors",
                    "author(s) id",
                    "authors with affiliations",
                ],
            },
            fix_record=_fix_csv_record,
            matches=_matches_csv,
            ignored_keys=frozenset(
                {
                    "conference date",
                    "conference location",
                    "conference code",
                    "publication stage",
                }
            ),
        ),
        "ris": FormatProfile(
            aliases={"publication_type": ["m3"], "pmid": ["c2"]},
            fix_record=_fix_ris_record,
            matches=_matches_ris,
        ),
    },
)
