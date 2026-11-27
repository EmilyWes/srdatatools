import difflib
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypeVar

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from app.gui.importing.parse_settings import DEFAULT_SETTINGS, ParseSettings
from app.helpers.authors import AuthorSlots, ids_by_key
from app.helpers.record_fields import SCALAR_FIELDS, DatePart, PagesBound, ScalarField
from app.models.record import Label, LabelValue, Record

logger = logging.getLogger(__name__)

_SUGGESTION_CUTOFF = 0.85

# Case-sensitive on purpose: "PMCID" is an ID header, "Valid" is not.
_ID_HEADER = re.compile(r"(?<![A-Za-z])[Ii][Dd](?![A-Za-z])|[A-Z]ID(?![A-Za-z])")
_KEYWORD_HEADER = re.compile(r"keywords?", re.IGNORECASE)

_DATE_PARTS = ("year", "month", "day")

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
    target: ScalarField


class DateRow(BaseModel):
    target: Literal["date"] = "date"
    part: DatePart = "full"


class PagesRow(BaseModel):
    target: Literal["pages"] = "pages"
    part: PagesBound | Literal["range", "count"] = "range"


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
    """prefix is a bare name; "" is no prefix."""

    target: Literal["keywords"] = "keywords"
    prefix: str = ""

    @field_validator("prefix")
    @classmethod
    def strip_brackets(cls, value: str) -> str:
        return value.strip().removeprefix("[").removesuffix("]").strip()


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

MatchKind = Literal["exact", "fuzzy", "id_fallback", "keyword_fallback"]

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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def default_other_id_key(header: str) -> str:
    return _slug(header) or "id"


def default_keyword_prefix(header: str) -> str:
    return _slug(_KEYWORD_HEADER.sub(" ", header))


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


def normalize_label(
    value: str, settings: ParseSettings = DEFAULT_SETTINGS
) -> LabelValue:
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
    settings: ParseSettings = DEFAULT_SETTINGS,
    split_authors: Mapping[str, list[str]] | None = None,
) -> Record:
    """A table cell is stored as one value, which cleaning splits; `split_authors`
    gives the names or affiliations of a key already split by the format."""
    mapping = ordered_mapping(mapping, settings.use_first)
    split_authors = split_authors or {}
    values: dict[str, Any] = {}
    other_ids: dict[str, str] = {}
    keywords: dict[str, list[str]] = {}
    labels: list[Label] = []
    author_ids: dict[str, list[str]] = {}
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
            values.setdefault(_classify_issn_isbn(row, value), [value])
        elif isinstance(row, OtherIdRow):
            other_ids[row.key] = value
        elif isinstance(row, KeywordsRow):
            keywords.setdefault(row.prefix, []).append(value)
        elif isinstance(row, AuthorsRow):
            if row.role != "ids":
                items = split_authors.get(key, [value])
                if items:
                    values.setdefault(_AUTHOR_FIELDS[row.role], items)
            elif row.id_key in author_ids:
                logger.warning(
                    "Ignoring %r: an earlier column gives %r", key, row.id_key
                )
            else:
                author_ids[row.id_key] = [value]

    return Record(
        **values,
        pages=_parse_pages(raw_fields, mapping),
        other_ids=other_ids,
        author_ids=author_ids,
        keywords=keywords,
        labels=labels,
        publication_date=_parse_publication_date(raw_fields, mapping),
    )


TagLines = list[tuple[str, str]]
# The name and affiliation lines to keep, plus each author's ids.
LineAuthors = Callable[[TagLines, dict[str, AuthorsRow]], tuple[TagLines, AuthorSlots]]


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
    """Each kept name and affiliation line is one author's; the ids come from the
    lines in order, so each stays with its author line rather than being matched
    by position. Each keyword, ISSN and ISBN line is a value of its own."""
    author_rows = dict(mapping.rows_of(AuthorsRow))
    kept, slots = author_lines(lines, author_rows)
    split_authors = {
        tag: [value for t, value in kept if t == tag]
        for tag, row in author_rows.items()
        if row.role != "ids"
    }
    keywords: dict[str, list[str]] = {}
    for key, row in mapping.rows_of(KeywordsRow):
        for line in (raw_fields.get(key) or "").splitlines():
            if line.strip():
                keywords.setdefault(row.prefix, []).append(line.strip())
    issn_isbn: dict[str, list[str]] = {}
    ordered = ordered_mapping(mapping, settings.use_first)
    for key, issn_row in ordered.rows_of(IssnIsbnRow):
        value = raw_fields.get(key) or ""
        items = [line.strip() for line in value.splitlines() if line.strip()]
        if items:
            issn_isbn.setdefault(_classify_issn_isbn(issn_row, value), items)
    rest = {
        key: row
        for key, row in mapping.rows.items()
        if not isinstance(row, KeywordsRow | IssnIsbnRow)
        and not (isinstance(row, AuthorsRow) and row.role == "ids")
    }
    record = apply_mapping(
        raw_fields, mapping.model_copy(update={"rows": rest}), settings, split_authors
    )
    return record.model_copy(
        update={"author_ids": ids_by_key(slots), "keywords": keywords, **issn_isbn}
    )


def override_aliases(
    base: Mapping[str, Suggest], overrides: Mapping[str, Suggest]
) -> dict[str, Suggest]:
    """An override only replaces the base alias of the same name; a base alias a
    profile doesn't want is left out through its ignored keys."""
    return {**base, **overrides}


def suggest_mapping(
    keys: list[str],
    suggestions: Mapping[str, Suggest],
    *,
    lenient: bool,
    ignored_keys: frozenset[str] = frozenset(),
) -> FieldMapping:
    """lenient adds fuzzy matching and ID- and keyword-header fallbacks, for
    free-text headers."""
    rows: dict[str, RowMapping] = {}
    match_kinds: dict[str, MatchKind] = {}
    for key in keys:
        normalized = key.strip().lower()
        if normalized in ignored_keys:
            continue
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
        elif lenient and _KEYWORD_HEADER.search(key):
            prefix = default_keyword_prefix(key)
            suggest = Suggest(KEYWORDS_TARGET, {"prefix": prefix})
            kind = "keyword_fallback"
        else:
            continue
        rows[key] = make_row(suggest, key)
        match_kinds[key] = kind
    return FieldMapping(rows=rows, match_kinds=match_kinds)
