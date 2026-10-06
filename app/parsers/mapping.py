import difflib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.models.record import Author, PartialDate, Record

logger = logging.getLogger(__name__)

_SUGGESTION_CUTOFF = 0.7

# Case-sensitive on purpose: "PMCID" is an ID header, "Valid" is not.
_ID_HEADER = re.compile(r"(?<![A-Za-z])[Ii][Dd](?![A-Za-z])|[A-Z]ID(?![A-Za-z])")

_MONTH_ABBREVIATIONS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_DATE_PATTERNS = [
    re.compile(r"^(?P<year>\d{4})$"),
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})$"),
]

SCALAR_FIELDS = frozenset(
    name for name, info in Record.model_fields.items() if info.annotation == str | None
)

LIST_TARGETS = ("authors", "keywords")
DATE_TARGETS = ("date", "year", "month", "day")
PAGE_TARGETS = ("page_start", "page_end")
EXCLUSIVE_TARGETS = (*DATE_TARGETS, *PAGE_TARGETS)
OTHER_IDS_PREFIX = "other_ids."


def _is_valid_target(target: str) -> bool:
    if target in SCALAR_FIELDS or target in LIST_TARGETS or target in EXCLUSIVE_TARGETS:
        return True
    return target.startswith(OTHER_IDS_PREFIX) and len(target) > len(OTHER_IDS_PREFIX)


@dataclass
class FieldMapping:
    targets: dict[str, str] = field(default_factory=dict)
    list_delimiter: str = ";"

    def __post_init__(self) -> None:
        for key, target in self.targets.items():
            if not _is_valid_target(target):
                raise ValueError(f"{key!r} maps to unknown Record field {target!r}")
        for target in EXCLUSIVE_TARGETS:
            keys = [k for k, t in self.targets.items() if t == target]
            if len(keys) > 1:
                raise ValueError(f"{target!r} is mapped from several inputs {keys}")

    def key_for(self, target: str) -> str | None:
        return next((k for k, t in self.targets.items() if t == target), None)


def _split_list(value: str, delimiter: str) -> list[str]:
    return [piece.strip() for piece in value.split(delimiter) if piece.strip()]


def _parse_int_field(value: str | None, field_name: str) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        logger.warning("Could not parse %s value %r", field_name, value)
        return None


def _parse_month(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    abbreviation = stripped[:3].lower()
    if abbreviation in _MONTH_ABBREVIATIONS:
        return _MONTH_ABBREVIATIONS[abbreviation]
    logger.warning("Could not parse month value %r", value)
    return None


def _build_partial_date(
    year: int | None, month: int | None, day: int | None
) -> PartialDate | None:
    if year is None and month is None and day is None:
        return None
    try:
        return PartialDate(year=year, month=month, day=day)
    except ValidationError:
        logger.warning("Dropping day %r because month is missing", day)
        return PartialDate(year=year, month=month, day=None)


def _parse_date_string(value: str) -> PartialDate | None:
    stripped = value.strip()
    for pattern in _DATE_PATTERNS:
        match = pattern.match(stripped)
        if match is None:
            continue
        parts = match.groupdict()
        return _build_partial_date(
            year=int(parts["year"]),
            month=int(parts["month"]) if parts.get("month") else None,
            day=int(parts["day"]) if parts.get("day") else None,
        )
    logger.warning("Could not parse date value %r", value)
    return None


def _parse_publication_date(
    raw_fields: dict[str, str], mapping: FieldMapping
) -> PartialDate | None:
    def cell(target: str) -> str | None:
        key = mapping.key_for(target)
        return raw_fields.get(key) if key is not None else None

    raw_date = cell("date")
    from_date = _parse_date_string(raw_date) if raw_date and raw_date.strip() else None
    year = _parse_int_field(cell("year"), "year")
    month = _parse_month(cell("month"))
    day = _parse_int_field(cell("day"), "day")
    if from_date is not None:
        year = year if year is not None else from_date.year
        month = month if month is not None else from_date.month
        day = day if day is not None else from_date.day
    return _build_partial_date(year, month, day)


def _join_pages(raw_fields: dict[str, str], mapping: FieldMapping) -> str | None:
    pieces = []
    for target in PAGE_TARGETS:
        key = mapping.key_for(target)
        value = (raw_fields.get(key) or "").strip() if key is not None else ""
        if value:
            pieces.append(value)
    return "-".join(pieces) or None


def apply_mapping(raw_fields: dict[str, str], mapping: FieldMapping) -> Record:
    values: dict[str, Any] = {}
    other_ids: dict[str, str] = {}
    author_names: list[str] = []
    keywords: list[str] = []
    for key, target in mapping.targets.items():
        value = (raw_fields.get(key) or "").strip()
        if not value:
            continue
        if target in SCALAR_FIELDS:
            values.setdefault(target, value)
        elif target.startswith(OTHER_IDS_PREFIX):
            other_ids[target.removeprefix(OTHER_IDS_PREFIX)] = value
        elif target == "authors":
            author_names.extend(_split_list(value, mapping.list_delimiter))
        elif target == "keywords":
            keywords.extend(_split_list(value, mapping.list_delimiter))

    if "pages" not in values:
        pages = _join_pages(raw_fields, mapping)
        if pages is not None:
            values["pages"] = pages

    return Record(
        **values,
        other_ids=other_ids,
        authors=[Author(full_name=name) for name in author_names],
        keywords=keywords,
        publication_date=_parse_publication_date(raw_fields, mapping),
    )


def default_other_id_key(header: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return slug or "id"


def suggest_mapping(
    keys: list[str], aliases: dict[str, list[str]], *, lenient: bool
) -> FieldMapping:
    """lenient adds fuzzy matching and an ID-header fallback, for free-text headers."""
    alias_to_target = {
        alias: target for target, names in aliases.items() for alias in names
    }

    targets: dict[str, str] = {}
    for key in keys:
        normalized = key.strip().lower()
        target = alias_to_target.get(normalized)
        if target is None and lenient:
            matches = difflib.get_close_matches(
                normalized, alias_to_target.keys(), n=1, cutoff=_SUGGESTION_CUTOFF
            )
            target = alias_to_target[matches[0]] if matches else None
            if target is None and _ID_HEADER.search(key):
                target = "other_ids"
        if target is None:
            continue
        if target == "other_ids":
            target = OTHER_IDS_PREFIX + default_other_id_key(key)
        if target in EXCLUSIVE_TARGETS and target in targets.values():
            continue
        targets[key] = target

    return FieldMapping(targets=targets)
