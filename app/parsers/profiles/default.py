from dataclasses import replace
from typing import Any

from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import ParseSettings

_SETTINGS = ParseSettings(skip_issn_isbn_qualifiers=True, minus_one_unlabeled=True)
_NBIB_SETTINGS = replace(_SETTINGS, keyword_prefixes={"MH": "[MeSH] "})

DEFAULT_PROFILES: dict[str, FormatProfile] = {
    file_type: FormatProfile(aliases={}, matches=never_matches, settings=settings)
    for file_type, settings in {
        "ris": _SETTINGS,
        "nbib": _NBIB_SETTINGS,
        "csv": _SETTINGS,
        "tsv": _SETTINGS,
        "excel": _SETTINGS,
        "bibtex": _SETTINGS,
    }.items()
}


def default_settings(file_type: str, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)
