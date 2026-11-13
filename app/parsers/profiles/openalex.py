import csv
from io import StringIO

from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile, never_matches
from app.parsers.profiles.default import (
    default_settings,
)

_CSV_MARKER_HEADERS = frozenset({"work id", "concept ids"})


def _matches_csv(text: str) -> bool:
    header = next(csv.reader(StringIO(text)), [])
    return _CSV_MARKER_HEADERS <= {column.strip().lower() for column in header}


# OpenAlex RIS and BibTeX exports carry nothing that marks them as OpenAlex.
OPENALEX = Profile(
    key="openalex",
    label="OpenAlex",
    formats={
        "csv": FormatProfile(
            suggestions={
                "author ids": Suggest(
                    "authors", {"role": "ids", "id_key": "openalex_author_id"}
                ),
                "source": Suggest("journal"),
                "concept": Suggest("keywords", {"prefix": "Concept"}),
                "topic": Suggest("keywords", {"prefix": "Topic"}),
                "type": Suggest("publication_type"),
                "work id": Suggest("other_ids", {"key": "openalex"}),
            },
            matches=_matches_csv,
            settings=default_settings("csv"),
        ),
        "ris": FormatProfile(
            suggestions={
                "c1": Suggest("authors", {"role": "affiliations"}),
            },
            matches=never_matches,
            settings=default_settings("ris"),
        ),
        "bibtex": FormatProfile(
            suggestions={},
            matches=never_matches,
            settings=default_settings("bibtex"),
        ),
    },
)
