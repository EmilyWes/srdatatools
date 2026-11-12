from collections.abc import Callable
from dataclasses import dataclass

from app.parsers.common import FileType
from app.parsers.mapping import Suggest
from app.parsers.quirks import ParseSettings

MatchesText = Callable[[str], bool]


@dataclass(frozen=True)
class FormatProfile:
    suggestions: dict[str, Suggest]
    matches: MatchesText
    settings: ParseSettings
    ignored_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    formats: dict[FileType, FormatProfile]


def never_matches(text: str) -> bool:
    return False
