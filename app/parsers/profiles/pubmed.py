import csv
import re
from io import StringIO

from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import default_settings
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
            aliases={"journal": ["jt", "bti"], "title": ["ti", "tt"]},
            matches=_matches_nbib,
            settings=default_settings(
                "nbib",
                continue_to_next=(
                    ContinueToNextField(
                        "title", frozenset({"[Not Available]."}), case_sensitive=True
                    ),
                ),
            ),
            quirks=(
                ExpandPageRange(),
                FirstValue("publication_type", "\n"),
                FirstValue("isbn", "\n"),
            ),
        ),
        "csv": FormatProfile(
            aliases={
                "journal": ["journal/book"],
                "other_ids.pmc": ["pmcid"],
                "other_ids.mid": ["nihms id"],
            },
            matches=_matches_csv,
            settings=default_settings("csv"),
            quirks=(DropEtAl(), StripLastAuthorTrailing(".")),
            list_delimiter=",",
        ),
    },
)
