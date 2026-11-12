import csv
import re
from io import StringIO

from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import (
    default_quirks,
    default_row_defaults,
    default_settings,
)
from app.parsers.quirks import CitationParts, StripLastAuthorTrailing

_NBIB_PMID_LINE = re.compile(r"^PMID ?- ", re.MULTILINE)
_NBIB_OWN_NLM_LINE = re.compile(r"^OWN ?- NLM\s*$", re.MULTILINE)
_CSV_HEADERS = {"pmid", "citation", "journal/book"}

CITATION_PARTS = CitationParts("Citation")


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
            row_defaults=default_row_defaults("nbib"),
            quirks=default_quirks("nbib"),
        ),
        "csv": FormatProfile(
            suggestions={
                "authors": Suggest("authors"),
                "journal/book": Suggest("journal"),
                "pmcid": Suggest("other_ids", {"key": "pmc"}),
                "nihms id": Suggest("other_ids", {"key": "mid"}),
            },
            matches=_matches_csv,
            settings=default_settings("csv"),
            row_defaults=default_row_defaults("csv", delimiter=","),
            quirks=default_quirks("csv", StripLastAuthorTrailing(), CITATION_PARTS),
        ),
    },
)
