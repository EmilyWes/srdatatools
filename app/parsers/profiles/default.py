from dataclasses import replace
from typing import Any

from app.parsers import bibtex, csv_, nbib, ris
from app.parsers.common import FileType
from app.parsers.mapping import LINE_DELIMITER, RowDefaults
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import (
    DropEtAl,
    ExpandPageRange,
    FirstValue,
    ParseSettings,
    RecordQuirk,
    StripDoi,
    StripPmid,
)

_SETTINGS = ParseSettings(
    issn_isbn_strip_extras=True,
    issn_isbn_only_one=True,
    empty_values=("[Not Available].",),
)
# PubMed writes one IS line per medium, e.g. "1234-5678 (Print)".
_NBIB_SETTINGS = replace(_SETTINGS, preferred_issn_qualifier="Electronic")

# Pages set runs last, so it also expands pages that another quirk filled.
_GENERIC_QUIRKS: tuple[RecordQuirk, ...] = (
    DropEtAl(),
    StripDoi(),
    StripPmid(),
    ExpandPageRange(),
)
_NBIB_QUIRKS: tuple[RecordQuirk, ...] = (
    DropEtAl(),
    StripDoi(),
    StripPmid(),
    FirstValue("publication_type", LINE_DELIMITER),
    ExpandPageRange(),
)

_TYPE_DEFAULTS: dict[
    FileType, tuple[ParseSettings, RowDefaults, tuple[RecordQuirk, ...]]
] = {
    "ris": (_SETTINGS, ris.ROW_DEFAULTS, _GENERIC_QUIRKS),
    "nbib": (_NBIB_SETTINGS, nbib.ROW_DEFAULTS, _NBIB_QUIRKS),
    "csv": (_SETTINGS, csv_.ROW_DEFAULTS, _GENERIC_QUIRKS),
    "tsv": (_SETTINGS, csv_.ROW_DEFAULTS, _GENERIC_QUIRKS),
    "excel": (_SETTINGS, csv_.ROW_DEFAULTS, _GENERIC_QUIRKS),
    "bibtex": (_SETTINGS, bibtex.ROW_DEFAULTS, _GENERIC_QUIRKS),
}
DEFAULT_PROFILES: dict[FileType, FormatProfile] = {
    file_type: FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=settings,
        row_defaults=row_defaults,
        quirks=quirks,
    )
    for file_type, (settings, row_defaults, quirks) in _TYPE_DEFAULTS.items()
}


def default_settings(file_type: FileType, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)


def default_row_defaults(file_type: FileType, **overrides: Any) -> RowDefaults:
    return replace(DEFAULT_PROFILES[file_type].row_defaults, **overrides)


def default_quirks(file_type: FileType, *own: RecordQuirk) -> tuple[RecordQuirk, ...]:
    """The Type's quirks plus the profile's own, with Pages set still last."""
    quirks = DEFAULT_PROFILES[file_type].quirks
    last = tuple(quirk for quirk in quirks if isinstance(quirk, ExpandPageRange))
    rest = tuple(quirk for quirk in quirks if not isinstance(quirk, ExpandPageRange))
    return rest + own + last
