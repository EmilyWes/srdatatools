from dataclasses import replace
from typing import Any

from app.parsers.common import FILE_TYPES, FileType
from app.parsers.profiles.base import FormatProfile, never_matches
from app.parsers.quirks import ParseSettings

DEFAULT_PROFILES: dict[FileType, FormatProfile] = {
    file_type: FormatProfile(
        suggestions={},
        matches=never_matches,
        # RIS DA usually holds more of the date than PY.
        settings=ParseSettings(use_first=("DA",) if file_type == "ris" else ()),
    )
    for file_type in FILE_TYPES
}


def default_settings(file_type: FileType, **overrides: Any) -> ParseSettings:
    return replace(DEFAULT_PROFILES[file_type].settings, **overrides)
