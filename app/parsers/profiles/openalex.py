import csv
from io import StringIO

from app.parsers.profiles.base import FormatProfile, Profile, never_matches
from app.parsers.profiles.default import default_settings
from app.parsers.quirks import FirstValue, ParallelAuthorColumns, StripPrefix

_LIST_DELIMITER = "|"
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
            aliases={
                "authors": ["author", "orcid", "author ids"],
                "journal": ["source"],
                "keywords": ["keyword", "concept", "topic"],
                "publication_type": ["type"],
                "other_ids.openalex": ["work id"],
            },
            matches=_matches_csv,
            settings=default_settings(
                "csv", keyword_prefixes={"Concept": "[Concept] ", "Topic": "[Topic] "}
            ),
            quirks=(
                ParallelAuthorColumns(
                    delimiter=_LIST_DELIMITER,
                    name_columns=("Author",),
                    orcid_column="ORCID",
                    orcid_prefix="https://orcid.org/",
                    id_column="Author IDs",
                    id_key="openalex_author_id",
                ),
                FirstValue("issn", _LIST_DELIMITER),
                StripPrefix("pmid", "https://pubmed.ncbi.nlm.nih.gov/"),
            ),
            list_delimiter=_LIST_DELIMITER,
            ignored_keys=frozenset(
                {
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
                    "pubmed",
                    "ror id",
                }
            ),
        ),
        "ris": FormatProfile(
            aliases={"authors": ["au", "c1"]},
            matches=never_matches,
            settings=default_settings("ris"),
        ),
        "bibtex": FormatProfile(
            aliases={},
            matches=never_matches,
            settings=default_settings("bibtex"),
            list_delimiter=",",
        ),
    },
)
