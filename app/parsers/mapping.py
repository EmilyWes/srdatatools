import difflib
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypeVar, get_args

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from app.models.record import Label, LabelValue, PartialDate, Record
from app.parsers.authors import (
    AUTHOR_JOINER,
    ID_JOINER,
    AuthorIds,
    format_author_ids,
    unsplit_author_ids,
)
from app.parsers.quirks import NO_QUIRKS, ParseSettings

logger = logging.getLogger(__name__)

_SUGGESTION_CUTOFF = 0.85

# Case-sensitive on purpose: "PMCID" is an ID header, "Valid" is not.
_ID_HEADER = re.compile(r"(?<![A-Za-z])[Ii][Dd](?![A-Za-z])|[A-Z]ID(?![A-Za-z])")

_TAGGED_KEYWORD = re.compile(r"\[([^\]]+)\] (.*)", re.DOTALL)
_UNSPLIT_KEYWORDS = re.compile(r"(?P<key>[^:\[\]]+):\[(?P<value>.*)\]", re.DOTALL)
# The key of unsplit keywords without a prefix.
UNPREFIXED_KEYWORDS_KEY = "keywords"

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
    # Also the stored YYYY/MM/DD, where any part after the year may be empty.
    re.compile(
        r"^(?P<year>\d{4})/(?P<month>\d{1,2}|[A-Za-z]{3,9})?/(?P<day>\d{1,2})?$"
    ),
    # RIS: YYYY/MM/DD/other, where every part after the year may be empty
    re.compile(r"^(?P<year>\d{4})/(?P<month>\d{1,2})?/(?P<day>\d{1,2})?/.*$"),
    # NBIB: YYYY Mon, YYYY Mon DD, YYYY Mon-Mon (a month range keeps its first month)
    re.compile(
        r"^(?P<year>\d{4}) (?P<month>[A-Za-z]{3,9})(?:-[A-Za-z]{3,9})?"
        r"(?: (?P<day>\d{1,2}))?$"
    ),
    re.compile(r"^(?P<day>\d{1,2}) (?P<month>[A-Za-z]{3,9})\.? (?P<year>\d{4})$"),
    re.compile(r"^(?P<month>[A-Za-z]{3,9})\.? (?P<day>\d{1,2}), (?P<year>\d{4})$"),
    # A season names no month: which months it covers depends on the hemisphere.
    re.compile(r"^(?:spring|summer|fall|autumn|winter) ?(?P<year>\d{4})$", re.I),
    re.compile(r"^(?P<month>[A-Za-z]{3,9})\.? ?(?P<year>\d{4})$"),
]
_NUMERIC_DATE = re.compile(
    r"^(?P<first>\d{1,2})(?P<sep>[/.-])(?P<second>\d{1,2})(?P=sep)(?P<year>\d{4})$"
)
_MAX_MONTH = 12
_DATE_PARTS = ("year", "month", "day")

DateOrder = Literal["eu", "us"]

ScalarTarget = Literal[
    "title",
    "abstract",
    "journal",
    "conference_name",
    "volume",
    "issue",
    "doi",
    "pmid",
    "publication_type",
    "language",
    "publisher",
    "url",
    "notes",
]
SCALAR_FIELDS = frozenset(get_args(ScalarTarget))

DATE_TARGET = "date"
PAGES_TARGET = "pages"
ISSN_ISBN_TARGET = "issn_isbn"
OTHER_IDS_TARGET = "other_ids"
AUTHORS_TARGET = "authors"
KEYWORDS_TARGET = "keywords"
LABEL_TARGET = "label"
DEFAULT_PHASE = "ft"
DEFAULT_SCREENER = "screener 1"
# RIS and NBIB repeat a tag per value.
LINE_DELIMITER = "\n"

AuthorRole = Literal["names", "ids", "affiliations"]
_AUTHOR_FIELDS = {"names": "author_names", "affiliations": "author_affiliations"}


class ScalarRow(BaseModel):
    target: ScalarTarget


class DateRow(BaseModel):
    target: Literal["date"] = "date"
    part: Literal["full", "year", "month", "day"] = "full"


class PagesRow(BaseModel):
    target: Literal["pages"] = "pages"
    part: Literal["range", "start", "end", "count"] = "range"


class IssnIsbnRow(BaseModel):
    target: Literal["issn_isbn"] = "issn_isbn"
    kind: Literal["auto", "issn", "isbn"] = "auto"


class OtherIdRow(BaseModel):
    target: Literal["other_ids"] = "other_ids"
    key: str = Field(min_length=1)


class AuthorsRow(BaseModel):
    target: Literal["authors"] = "authors"
    role: AuthorRole = "names"
    id_key: str = Field(min_length=1)


class KeywordsRow(BaseModel):
    """prefix is a bare name; keywords get it as "[name] keyword", so an export can
    split the prefix off again."""

    target: Literal["keywords"] = "keywords"
    prefix: str = ""

    @field_validator("prefix")
    @classmethod
    def strip_brackets(cls, value: str) -> str:
        return value.strip().removeprefix("[").removesuffix("]").strip()


def tag_keyword(prefix: str, keyword: str) -> str:
    return f"[{prefix}] {keyword}" if prefix else keyword


def split_keyword(keyword: str) -> tuple[str | None, str]:
    match = _TAGGED_KEYWORD.fullmatch(keyword)
    return (match[1], match[2]) if match else (None, keyword)


def unsplit_keywords(prefix: str, value: str) -> str:
    """A column holding all of a record's keywords, stored as "prefix:[value]"
    until cleaning splits it."""
    return f"{prefix or UNPREFIXED_KEYWORDS_KEY}:[{value}]"


def parse_unsplit_keywords(keyword: str) -> tuple[str, str] | None:
    """The prefix ("" for none) and the unsplit value."""
    match = _UNSPLIT_KEYWORDS.fullmatch(keyword)
    if match is None:
        return None
    key = match["key"]
    return ("" if key == UNPREFIXED_KEYWORDS_KEY else key), match["value"]


class LabelRow(BaseModel):
    target: Literal["label"] = "label"
    phase: str = DEFAULT_PHASE
    screener: str = DEFAULT_SCREENER


RowMapping = Annotated[
    ScalarRow
    | DateRow
    | PagesRow
    | IssnIsbnRow
    | OtherIdRow
    | AuthorsRow
    | KeywordsRow
    | LabelRow,
    Field(discriminator="target"),
]
_ROW_ADAPTER: TypeAdapter[RowMapping] = TypeAdapter(RowMapping)

TARGETS = (
    *sorted(SCALAR_FIELDS),
    DATE_TARGET,
    PAGES_TARGET,
    ISSN_ISBN_TARGET,
    OTHER_IDS_TARGET,
    AUTHORS_TARGET,
    KEYWORDS_TARGET,
    LABEL_TARGET,
)

MatchKind = Literal["exact", "fuzzy", "id_fallback"]

_Row = TypeVar("_Row", bound=BaseModel)


class FieldMapping(BaseModel):
    rows: dict[str, RowMapping] = Field(default_factory=dict)
    match_kinds: dict[str, MatchKind] = Field(default_factory=dict)

    def rows_of(self, row_type: type[_Row]) -> list[tuple[str, _Row]]:
        return [(k, row) for k, row in self.rows.items() if isinstance(row, row_type)]


@dataclass(frozen=True)
class Suggest:
    """A suggested row: its target plus any options that differ from the defaults."""

    target: str
    options: Mapping[str, str] = field(default_factory=dict)


def default_other_id_key(header: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return slug or "id"


def default_row(target: str, key: str) -> RowMapping:
    if target == DATE_TARGET:
        return DateRow()
    if target == PAGES_TARGET:
        return PagesRow()
    if target == ISSN_ISBN_TARGET:
        return IssnIsbnRow()
    if target == OTHER_IDS_TARGET:
        return OtherIdRow(key=default_other_id_key(key))
    if target == AUTHORS_TARGET:
        return AuthorsRow(id_key=default_other_id_key(key))
    if target == KEYWORDS_TARGET:
        return KeywordsRow()
    if target == LABEL_TARGET:
        return LabelRow()
    if target in SCALAR_FIELDS:
        return ScalarRow.model_validate({"target": target})
    raise ValueError(f"{key!r} maps to unknown Record field {target!r}")


def row_with(row: RowMapping, options: Mapping[str, str]) -> RowMapping:
    return _ROW_ADAPTER.validate_python({**row.model_dump(), **options})


def make_row(suggest: Suggest, key: str) -> RowMapping:
    return row_with(default_row(suggest.target, key), suggest.options)


_LABEL_SPELLINGS: dict[str, LabelValue] = {
    **dict.fromkeys(
        ("include", "included", "yes", "y", "1", "true", "relevant"), "include"
    ),
    **dict.fromkeys(
        ("exclude", "excluded", "no", "n", "0", "false", "irrelevant"), "exclude"
    ),
    **dict.fromkeys(("maybe", "unsure", "undecided", "?"), "maybe"),
    # ASReview writes -1 for records nobody has labeled yet.
    **dict.fromkeys(("", "-1"), "unlabeled"),
}

# Hyphens may sit anywhere in an ID; a qualifier like "(Print)" may follow it.
ISSN_ISBN_TOKEN = re.compile(
    r"(?<![\w-])(?P<id>\d[\d-]*[\dXx])(?![\w-])(?:\s*\((?P<qualifier>[^)]*)\))?"
)
ISSN_LENGTH = 8
ISBN_LENGTHS = (10, 13)


def _label_for_line(line: str, settings: ParseSettings) -> LabelValue | None:
    normalized = line.strip().lower()
    custom = settings.label_lookup
    if normalized in custom:
        return custom[normalized]
    return _LABEL_SPELLINGS.get(normalized)


def normalize_label(value: str, settings: ParseSettings = NO_QUIRKS) -> LabelValue:
    """In a multi-line value (RIS N1 notes) the first line that is a label wins;
    the other lines are usually unrelated notes, so none matching is unlabeled."""
    lines = [line for line in value.splitlines() if line.strip()]
    if len(lines) > 1:
        labels = (_label_for_line(line, settings) for line in lines)
        return next((label for label in labels if label is not None), "unlabeled")
    label = _label_for_line(value, settings)
    if label is None:
        logger.warning("Unknown label value %r", value)
        return "unknown"
    return label


def _classify_issn_isbn(row: IssnIsbnRow, value: str) -> str:
    """The whole value is kept; cleaning strips it. Auto goes by the first
    ISSN- or ISBN-length number."""
    if row.kind != "auto":
        return row.kind
    for token in ISSN_ISBN_TOKEN.finditer(value):
        length = len(token["id"].replace("-", ""))
        if length == ISSN_LENGTH:
            return "issn"
        if length in ISBN_LENGTHS:
            return "isbn"
    logger.warning("Value %r is neither an ISSN nor an ISBN", value)
    return "issn"


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


def _parse_numeric_date(match: re.Match[str], order: DateOrder) -> PartialDate | None:
    """The order only decides when both numbers could be the month."""
    first, second = int(match["first"]), int(match["second"])
    if first > _MAX_MONTH and second > _MAX_MONTH:
        logger.warning("Could not parse date value %r", match.string)
        return None
    if first > _MAX_MONTH or (second <= _MAX_MONTH and order == "eu"):
        day, month = first, second
    else:
        month, day = first, second
    return _build_partial_date(int(match["year"]), month, day)


def parse_date_string(value: str, order: DateOrder = "eu") -> PartialDate | None:
    stripped = value.strip()
    numeric = _NUMERIC_DATE.match(stripped)
    if numeric is not None:
        return _parse_numeric_date(numeric, order)
    for pattern in _DATE_PATTERNS:
        match = pattern.match(stripped)
        if match is None:
            continue
        parts = match.groupdict()
        return _build_partial_date(
            year=int(parts["year"]),
            month=_parse_month(parts.get("month")),
            day=int(parts["day"]) if parts.get("day") else None,
        )
    logger.warning("Could not parse date value %r", value)
    return None


def _parse_publication_date(
    raw_fields: dict[str, str], mapping: FieldMapping
) -> str | None:
    """A full date is copied as it is; without one the year, month and day parts
    are joined as YYYY/MM/DD, a missing part left empty. Each comes from the
    first row giving it; cleaning reads the values."""
    parts: dict[str, str] = {}
    for key, row in mapping.rows_of(DateRow):
        value = (raw_fields.get(key) or "").strip()
        if value:
            parts.setdefault(row.part, value)
    if "full" in parts:
        return parts["full"]
    if not parts:
        return None
    return "/".join(parts.get(part, "") for part in _DATE_PARTS)


def _parse_pages(raw_fields: dict[str, str], mapping: FieldMapping) -> str | None:
    parts: dict[str, str] = {}
    for key, row in mapping.rows_of(PagesRow):
        value = (raw_fields.get(key) or "").strip()
        if value:
            parts.setdefault(row.part, value)
    if "range" in parts:
        return parts["range"]
    start, end, count = parts.get("start"), parts.get("end"), parts.get("count")
    if start and count and not end:
        try:
            end = str(int(start) + int(count) - 1)
        except ValueError:
            logger.warning("Could not add %r pages to start page %r", count, start)
    return "-".join(piece for piece in (start, end) if piece) or None


def ordered_mapping(mapping: FieldMapping, use_first: tuple[str, ...]) -> FieldMapping:
    first = {key: mapping.rows[key] for key in use_first if key in mapping.rows}
    return mapping.model_copy(update={"rows": {**first, **mapping.rows}})


def apply_mapping(
    raw_fields: dict[str, str],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> Record:
    mapping = ordered_mapping(mapping, settings.use_first)
    values: dict[str, Any] = {}
    other_ids: dict[str, str] = {}
    keywords: list[str] = []
    labels: list[Label] = []
    author_ids: list[str] = []
    for key, row in mapping.rows.items():
        value = (raw_fields.get(key) or "").strip()
        if isinstance(row, LabelRow):
            labels.append(
                Label(
                    phase=row.phase,
                    screener=row.screener,
                    value=normalize_label(value, settings),
                )
            )
            continue
        if not value:
            continue
        if isinstance(row, ScalarRow):
            values.setdefault(row.target, value)
        elif isinstance(row, IssnIsbnRow):
            values.setdefault(_classify_issn_isbn(row, value), value)
        elif isinstance(row, OtherIdRow):
            other_ids[row.key] = value
        elif isinstance(row, KeywordsRow):
            keywords.append(unsplit_keywords(row.prefix, value))
        elif isinstance(row, AuthorsRow):
            if row.role == "ids":
                author_ids.append(unsplit_author_ids(row.id_key, value))
            else:
                values.setdefault(_AUTHOR_FIELDS[row.role], value)

    return Record(
        **values,
        pages=_parse_pages(raw_fields, mapping),
        other_ids=other_ids,
        author_ids=ID_JOINER.join(author_ids) or None,
        keywords=keywords,
        labels=labels,
        publication_date=_parse_publication_date(raw_fields, mapping),
    )


TagLines = list[tuple[str, str]]
# The name and affiliation lines to keep, plus each author's ids.
LineAuthors = Callable[[TagLines, dict[str, AuthorsRow]], tuple[TagLines, AuthorIds]]


def join_tag_lines(lines: TagLines) -> dict[str, str]:
    """A tag repeated per value (RIS, NBIB) becomes one raw field, one value a line."""
    values: dict[str, list[str]] = {}
    for tag, value in lines:
        values.setdefault(tag, []).append(value)
    return {
        tag: "\n".join(v for v in tag_values if v) for tag, tag_values in values.items()
    }


def apply_line_mapping(
    lines: TagLines,
    raw_fields: dict[str, str],
    mapping: FieldMapping,
    settings: ParseSettings,
    author_lines: LineAuthors,
) -> Record:
    """The kept name and affiliation lines are joined with AUTHOR_JOINER; the ids
    come from the lines in order, so each stays with its author line rather than
    being matched by position. Each keyword line is a keyword."""
    author_rows = dict(mapping.rows_of(AuthorsRow))
    kept, author_ids = author_lines(lines, author_rows)
    joined = {
        tag: AUTHOR_JOINER.join(value for t, value in kept if t == tag)
        for tag, row in author_rows.items()
        if row.role != "ids"
    }
    keywords = [
        tag_keyword(row.prefix, line.strip())
        for key, row in mapping.rows_of(KeywordsRow)
        for line in (raw_fields.get(key) or "").splitlines()
        if line.strip()
    ]
    rest = {
        key: row
        for key, row in mapping.rows.items()
        if not isinstance(row, KeywordsRow)
        and not (isinstance(row, AuthorsRow) and row.role == "ids")
    }
    record = apply_mapping(
        {**raw_fields, **joined},
        mapping.model_copy(update={"rows": rest}),
        settings,
    )
    return record.model_copy(
        update={"author_ids": format_author_ids(author_ids), "keywords": keywords}
    )


def override_aliases(
    base: Mapping[str, Suggest], overrides: Mapping[str, Suggest]
) -> dict[str, Suggest]:
    """A target the overrides suggest for drops every base alias of that target."""
    replaced = {suggest.target for suggest in overrides.values()}
    kept = {a: s for a, s in base.items() if s.target not in replaced}
    return {**kept, **overrides}


def suggest_mapping(
    keys: list[str],
    suggestions: Mapping[str, Suggest],
    *,
    lenient: bool,
) -> FieldMapping:
    """lenient adds fuzzy matching and an ID-header fallback, for free-text headers."""
    rows: dict[str, RowMapping] = {}
    match_kinds: dict[str, MatchKind] = {}
    for key in keys:
        normalized = key.strip().lower()
        kind: MatchKind = "exact"
        alias = normalized if normalized in suggestions else None
        if alias is None and lenient:
            matches = difflib.get_close_matches(
                normalized, suggestions.keys(), n=1, cutoff=_SUGGESTION_CUTOFF
            )
            alias = matches[0] if matches else None
            kind = "fuzzy"
        if alias is not None:
            suggest = suggestions[alias]
        elif lenient and _ID_HEADER.search(key):
            suggest, kind = Suggest(OTHER_IDS_TARGET), "id_fallback"
        else:
            continue
        rows[key] = make_row(suggest, key)
        match_kinds[key] = kind
    return FieldMapping(rows=rows, match_kinds=match_kinds)
