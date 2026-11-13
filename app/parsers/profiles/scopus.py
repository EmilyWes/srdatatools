import csv
import re
from io import StringIO

from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import (
    default_settings,
)

_AUTHOR_KEYWORD_PREFIX = "Author"
_AUTHOR_ID_KEY = "scopus_author_id"

_CSV_EID_HEADER = "eid"
_RIS_DB_LINE = re.compile(r"^DB  - Scopus\s*$", re.MULTILINE)
_BIBTEX_SOURCE_FIELD = re.compile(
    r"^\s*source\s*=\s*\{Scopus\}", re.MULTILINE | re.IGNORECASE
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
            suggestions={
                "author full names": Suggest("authors"),
                "author(s) id": Suggest(
                    "authors", {"role": "ids", "id_key": _AUTHOR_ID_KEY}
                ),
                "authors with affiliations": Suggest(
                    "authors", {"role": "affiliations"}
                ),
                "author keywords": Suggest(
                    "keywords", {"prefix": _AUTHOR_KEYWORD_PREFIX}
                ),
                "index keywords": Suggest("keywords"),
            },
            matches=_matches_csv,
            settings=default_settings("csv"),
            # "Authors" abbreviates the given names in "Author full names".
            ignored_keys=frozenset({"authors"}),
        ),
        "ris": FormatProfile(
            suggestions={
                "m3": Suggest("publication_type"),
                "c2": Suggest("pmid"),
            },
            matches=_matches_ris,
            settings=default_settings("ris"),
            # TY is only the RIS reference type (JOUR); M3 holds Scopus's own.
            ignored_keys=frozenset({"ty"}),
        ),
        "bibtex": FormatProfile(
            suggestions={
                "type": Suggest("publication_type"),
                "pmid": Suggest("pmid"),
                "author_keywords": Suggest(
                    "keywords", {"prefix": _AUTHOR_KEYWORD_PREFIX}
                ),
                "keywords": Suggest("keywords"),
            },
            matches=_matches_bibtex,
            settings=default_settings("bibtex"),
            # The entry type (@article) is less precise than Scopus's own type.
            ignored_keys=frozenset({"@type"}),
        ),
    },
)
