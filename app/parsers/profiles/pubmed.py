import csv
import re
from io import StringIO

from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import (
    default_settings,
)

_NBIB_PMID_LINE = re.compile(r"^PMID ?- ", re.MULTILINE)
_NBIB_OWN_NLM_LINE = re.compile(r"^OWN ?- NLM\s*$", re.MULTILINE)
_CSV_HEADERS = {"pmid", "citation", "journal/book"}


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
            suggestions={
                "jt": Suggest("journal"),
                "bti": Suggest("journal"),
                "ti": Suggest("title"),
                "tt": Suggest("title"),
            },
            matches=_matches_nbib,
            settings=default_settings("nbib"),
            # TA abbreviates the journal name in JT.
            ignored_keys=frozenset({"ta"}),
        ),
        "csv": FormatProfile(
            suggestions={
                "nihms id": Suggest("other_ids", {"key": "mid"}),
            },
            matches=_matches_csv,
            settings=default_settings("csv"),
        ),
    },
)
