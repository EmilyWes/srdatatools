from dataclasses import replace
from typing import Any

from app.parsers import bibtex, csv_, nbib, ris
from app.parsers.common import FileType
from app.parsers.mapping import RowDefaults
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import ParseSettings

_ROW_DEFAULTS: dict[FileType, RowDefaults] = {
    "ris": ris.ROW_DEFAULTS,
    "nbib": nbib.ROW_DEFAULTS,
    "csv": csv_.ROW_DEFAULTS,
    "tsv": csv_.ROW_DEFAULTS,
    "excel": csv_.ROW_DEFAULTS,
    "bibtex": bibtex.ROW_DEFAULTS,
}
DEFAULT_PROFILES: dict[FileType, FormatProfile] = {
    file_type: FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=ParseSettings(),
        row_defaults=row_defaults,
    )
    for file_type, row_defaults in _ROW_DEFAULTS.items()
}


def default_settings(file_type: FileType, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)


def default_row_defaults(file_type: FileType, **overrides: Any) -> RowDefaults:
    return replace(DEFAULT_PROFILES[file_type].row_defaults, **overrides)
