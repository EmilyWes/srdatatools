from dataclasses import replace
from typing import Any

from app.parsers import bibtex, csv_, nbib, ris
from app.parsers.mapping import LINE_DELIMITER, RowDefaults
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import (
    ContinueToNextField,
    DropEtAl,
    ExpandPageRange,
    FirstValue,
    ParseSettings,
    RecordQuirk,
    StripPrefix,
)

_SETTINGS = ParseSettings(
    skip_issn_isbn_qualifiers=True,
    minus_one_unlabeled=True,
    continue_to_next=(
        ContinueToNextField(
            "title", frozenset({"[Not Available]."}), case_sensitive=True
        ),
    ),
)
# PubMed writes one IS line per medium, e.g. "1234-5678 (Print)".
_NBIB_SETTINGS = replace(_SETTINGS, preferred_issn_qualifier="Electronic")

_GENERIC_QUIRKS: tuple[RecordQuirk, ...] = (
    FirstValue("isbn", LINE_DELIMITER),
    FirstValue("issn", "|"),
    DropEtAl(),
    StripPrefix("pmid", "https://pubmed.ncbi.nlm.nih.gov/"),
    ExpandPageRange(),
)
_NBIB_QUIRKS: tuple[RecordQuirk, ...] = (
    *_GENERIC_QUIRKS,
    FirstValue("publication_type", LINE_DELIMITER),
)

DEFAULT_PROFILES: dict[str, FormatProfile] = {
    file_type: FormatProfile(
        suggestions={},
        matches=never_matches,
        settings=settings,
        row_defaults=row_defaults,
        quirks=quirks,
    )
    for file_type, (settings, row_defaults, quirks) in {
        "ris": (_SETTINGS, ris.ROW_DEFAULTS, _GENERIC_QUIRKS),
        "nbib": (_NBIB_SETTINGS, nbib.ROW_DEFAULTS, _NBIB_QUIRKS),
        "csv": (_SETTINGS, csv_.ROW_DEFAULTS, _GENERIC_QUIRKS),
        "tsv": (_SETTINGS, csv_.ROW_DEFAULTS, _GENERIC_QUIRKS),
        "excel": (_SETTINGS, csv_.ROW_DEFAULTS, _GENERIC_QUIRKS),
        "bibtex": (_SETTINGS, bibtex.ROW_DEFAULTS, _GENERIC_QUIRKS),
    }.items()
}


def default_settings(file_type: str, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)


def default_row_defaults(file_type: str, **overrides: Any) -> RowDefaults:
    return replace(DEFAULT_PROFILES[file_type].row_defaults, **overrides)


def default_quirks(file_type: str, *own: RecordQuirk) -> tuple[RecordQuirk, ...]:
    return DEFAULT_PROFILES[file_type].quirks + own
