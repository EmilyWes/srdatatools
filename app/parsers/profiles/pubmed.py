import csv
import re
from io import StringIO

from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import default_row_defaults, default_settings
from app.parsers.quirks import (
    ContinueToNextField,
    DropEtAl,
    ExpandPageRange,
    FirstValue,
    StripLastAuthorTrailing,
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
            settings=default_settings(
                "nbib",
                continue_to_next=(
                    ContinueToNextField(
                        "title", frozenset({"[Not Available]."}), case_sensitive=True
                    ),
                ),
            ),
            row_defaults=default_row_defaults("nbib"),
            quirks=(
                ExpandPageRange(),
                FirstValue("publication_type", "\n"),
                FirstValue("isbn", "\n"),
            ),
        ),
        "csv": FormatProfile(
            suggestions={
                "authors": Suggest("authors", {"role": "full_name"}),
                "journal/book": Suggest("journal"),
                "pmcid": Suggest("other_ids", {"key": "pmc"}),
                "nihms id": Suggest("other_ids", {"key": "mid"}),
            },
            matches=_matches_csv,
            settings=default_settings("csv"),
            row_defaults=default_row_defaults("csv", delimiter=","),
            quirks=(DropEtAl(), StripLastAuthorTrailing(".")),
        ),
    },
)
