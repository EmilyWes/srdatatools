from dataclasses import replace
from typing import Any

from app.parsers import bibtex, csv_, nbib, ris
from app.parsers.mapping import RowDefaults
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import ParseSettings

_SETTINGS = ParseSettings(skip_issn_isbn_qualifiers=True, minus_one_unlabeled=True)

DEFAULT_PROFILES: dict[str, FormatProfile] = {
    file_type: FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=_SETTINGS,
        row_defaults=row_defaults,
    )
    for file_type, row_defaults in {
        "ris": ris.ROW_DEFAULTS,
        "nbib": nbib.ROW_DEFAULTS,
        "csv": csv_.ROW_DEFAULTS,
        "tsv": csv_.ROW_DEFAULTS,
        "excel": csv_.ROW_DEFAULTS,
        "bibtex": bibtex.ROW_DEFAULTS,
    }.items()
}


def default_settings(file_type: str, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)


def default_row_defaults(file_type: str, **overrides: Any) -> RowDefaults:
    return replace(DEFAULT_PROFILES[file_type].row_defaults, **overrides)
