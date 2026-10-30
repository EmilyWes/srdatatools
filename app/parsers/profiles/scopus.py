import csv
import re
from io import StringIO

from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import default_settings
from app.parsers.quirks import IdFromUrl, ParallelAuthorColumns, RisNotes

_AUTHOR_KEYWORD_PREFIX = "[Author] "

_CSV_EID_HEADER = "eid"
_RIS_DB_LINE = re.compile(r"^DB  - Scopus\s*$", re.MULTILINE)
_BIBTEX_SOURCE_FIELD = re.compile(
    r"^\s*source\s*=\s*\{Scopus\}", re.MULTILINE | re.IGNORECASE
)
# Current exports link .../pages/publications/<n>; older ones .../record.uri?eid=...
_URL_EID = re.compile(
    r"scopus\.com/(?:pages/publications/|inward/record\.uri\?.*?\beid=2-s2\.0-)(\d+)"
)


def _matches_csv(text: str) -> bool:
    header = next(csv.reader(StringIO(text)), [])
    return _CSV_EID_HEADER in {column.strip().lower() for column in header}


def _matches_ris(text: str) -> bool:
    return bool(_RIS_DB_LINE.search(text))


def _matches_bibtex(text: str) -> bool:
    return bool(_BIBTEX_SOURCE_FIELD.search(text))


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
            matches=_matches_csv,
            settings=default_settings(
                "csv", keyword_prefixes={"Author Keywords": _AUTHOR_KEYWORD_PREFIX}
            ),
            quirks=(
                ParallelAuthorColumns(
                    delimiter=";",
                    name_columns=("Author full names", "Authors"),
                    name_separator=",",
                    embedded_ids=True,
                    id_column="Author(s) ID",
                    id_key="scopus_author_id",
                    affiliation_column="Authors with affiliations",
                ),
            ),
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
            matches=_matches_ris,
            settings=default_settings("ris"),
            quirks=(
                RisNotes(
                    "N1",
                    {"EID: ": "other_ids.eid", "Conference name: ": "conference_name"},
                ),
            ),
        ),
        "bibtex": FormatProfile(
            aliases={
                "publication_type": ["type"],
                "pmid": ["pmid"],
                "keywords": ["author_keywords", "keywords"],
            },
            matches=_matches_bibtex,
            settings=default_settings(
                "bibtex", keyword_prefixes={"author_keywords": _AUTHOR_KEYWORD_PREFIX}
            ),
            quirks=(IdFromUrl("url", _URL_EID, "eid", "2-s2.0-"),),
        ),
    },
)
