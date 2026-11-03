import csv
import re
from io import StringIO

from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import default_row_defaults, default_settings
from app.parsers.quirks import (
    AffiliationLeadingName,
    EmbeddedAuthorIds,
    IdFromUrl,
    RisNotes,
)

_AUTHOR_KEYWORD_PREFIX = "[Author] "
_AUTHOR_ID_KEY = "scopus_author_id"

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
            row_defaults=default_row_defaults("csv"),
            quirks=(EmbeddedAuthorIds(_AUTHOR_ID_KEY), AffiliationLeadingName()),
            # "Authors" abbreviates the given names in "Author full names".
            ignored_keys=frozenset(
                {
                    "authors",
                    "conference date",
                    "conference location",
                    "conference code",
                    "publication stage",
                }
            ),
        ),
        "ris": FormatProfile(
            suggestions={
                "m3": Suggest("publication_type"),
                "c2": Suggest("pmid"),
            },
            matches=_matches_ris,
            settings=default_settings("ris"),
            row_defaults=default_row_defaults("ris"),
            quirks=(
                RisNotes(
                    "N1",
                    {"EID: ": "other_ids.eid", "Conference name: ": "conference_name"},
                ),
            ),
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
            row_defaults=default_row_defaults("bibtex"),
            quirks=(IdFromUrl("url", _URL_EID, "eid", "2-s2.0-"),),
        ),
    },
)
