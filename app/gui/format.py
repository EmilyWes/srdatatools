import json
from typing import Literal

from app.parsers.profiles import PROFILES

_UNKNOWN_SOURCE = "Unknown"
_LABEL_PREFIX = "label:"
_KEYWORD_PREFIX = "keywords:"
_LABEL_NUMBERS = {
    "include": "1",
    "exclude": "0",
    "maybe": "0.5",
    "unknown": "?",
}

LabelFormat = Literal["words", "numbers"]


def format_count(count: int) -> str:
    return f"{count:,}".replace(",", ".")


def source_label(source: str | None) -> str:
    if source is None:
        return _UNKNOWN_SOURCE
    profile = PROFILES.get(source)
    return profile.label if profile is not None else source


def label_key(phase: str, screener: str) -> str:
    """Identifies a label phase + screener in the table and dashboard settings."""
    return _LABEL_PREFIX + json.dumps([phase, screener])


def is_label_key(key: str) -> bool:
    return key.startswith(_LABEL_PREFIX)


def label_pair(key: str) -> tuple[str, str]:
    phase, screener = json.loads(key.removeprefix(_LABEL_PREFIX))
    return phase, screener


def keyword_key(prefix: str | None) -> str:
    """Identifies a keyword prefix (None: unprefixed) in the table and dashboard
    settings."""
    return _KEYWORD_PREFIX + json.dumps(prefix)


def is_keyword_key(key: str) -> bool:
    return key.startswith(_KEYWORD_PREFIX)


def keyword_prefix(key: str) -> str | None:
    prefix: str | None = json.loads(key.removeprefix(_KEYWORD_PREFIX))
    return prefix


def label_text(value: str, label_format: LabelFormat) -> str:
    if value == "unlabeled":
        return ""
    return _LABEL_NUMBERS[value] if label_format == "numbers" else value
