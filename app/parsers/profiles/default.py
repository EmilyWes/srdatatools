from dataclasses import replace
from typing import Any

from app.parsers import bibtex, csv_, nbib, ris
from app.parsers.mapping import RowDefaults
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import ParseSettings

_SETTINGS = ParseSettings(skip_issn_isbn_qualifiers=True, minus_one_unlabeled=True)
# PubMed writes one IS line per medium, e.g. "1234-5678 (Print)".
_NBIB_SETTINGS = replace(_SETTINGS, preferred_issn_qualifier="Electronic")

DEFAULT_PROFILES: dict[str, FormatProfile] = {
    file_type: FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=settings,
        row_defaults=row_defaults,
    )
    for file_type, (settings, row_defaults) in {
        "ris": (_SETTINGS, ris.ROW_DEFAULTS),
        "nbib": (_NBIB_SETTINGS, nbib.ROW_DEFAULTS),
        "csv": (_SETTINGS, csv_.ROW_DEFAULTS),
        "tsv": (_SETTINGS, csv_.ROW_DEFAULTS),
        "excel": (_SETTINGS, csv_.ROW_DEFAULTS),
        "bibtex": (_SETTINGS, bibtex.ROW_DEFAULTS),
    }.items()
}


def default_settings(file_type: str, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)


def default_row_defaults(file_type: str, **overrides: Any) -> RowDefaults:
    return replace(DEFAULT_PROFILES[file_type].row_defaults, **overrides)
