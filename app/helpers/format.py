import json
from typing import Literal

# Between the values of a list, wherever one is shown or exported.
DISPLAY_SEPARATOR = "; "
_LABEL_PREFIX = "label:"
_KEYWORD_PREFIX = "keywords:"
_AUTHOR_ID_PREFIX = "author_ids:"
_LABEL_NUMBERS = {
    "include": "1",
    "exclude": "0",
    "maybe": "0.5",
    "unknown": "?",
}

LabelFormat = Literal["words", "numbers"]


def format_count(count: int) -> str:
    return f"{count:,}".replace(",", ".")


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


def author_id_key(id_key: str) -> str:
    """Identifies an author-ID key not yet split by cleaning in the table settings."""
    return _AUTHOR_ID_PREFIX + json.dumps(id_key)


def is_author_id_key(key: str) -> bool:
    return key.startswith(_AUTHOR_ID_PREFIX)


def author_id_name(key: str) -> str:
    name: str = json.loads(key.removeprefix(_AUTHOR_ID_PREFIX))
    return name


def label_text(value: str, label_format: LabelFormat) -> str:
    if value == "unlabeled":
        return ""
    return _LABEL_NUMBERS[value] if label_format == "numbers" else value
