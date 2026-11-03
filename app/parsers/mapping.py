import difflib
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypeVar, get_args

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.models.record import (
    Affiliation,
    Author,
    Label,
    LabelValue,
    PartialDate,
    Record,
)
from app.parsers.authors import author_from_name
from app.parsers.quirks import NO_QUIRKS, ParseSettings

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
DEFAULT_NAME_SEPARATOR = ","
# RIS and NBIB repeat a tag per value, and BibTeX authors are split before mapping.
LINE_DELIMITER = "\n"

AuthorRole = Literal[
    "full_name", "first_last", "last_first", "orcid", "ids", "affiliations"
]
NAME_ROLES: tuple[AuthorRole, ...] = ("full_name", "first_last", "last_first")
_ORCID_URL = re.compile(r"^https?://orcid\.org/")


class ScalarRow(BaseModel):
    target: ScalarTarget


class DateRow(BaseModel):
    target: Literal["date"] = "date"
    part: Literal["full", "year", "month", "day"] = "full"
    order: DateOrder = "eu"


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
    role: AuthorRole = "last_first"
    delimiter: str
    separator: str = DEFAULT_NAME_SEPARATOR
    id_key: str = Field(min_length=1)


class KeywordsRow(BaseModel):
    target: Literal["keywords"] = "keywords"
    delimiter: str
    prefix: str = ""


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
class RowDefaults:
    delimiter: str = ";"
    author_delimiter: str | None = None
    date_order: DateOrder = "eu"


@dataclass(frozen=True)
class Suggest:
    """A suggested row: its target plus any options that differ from the defaults."""

    target: str
    options: Mapping[str, str] = field(default_factory=dict)


def default_other_id_key(header: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return slug or "id"


def default_row(target: str, key: str, defaults: RowDefaults) -> RowMapping:
    if target == DATE_TARGET:
        return DateRow(order=defaults.date_order)
    if target == PAGES_TARGET:
        return PagesRow()
    if target == ISSN_ISBN_TARGET:
        return IssnIsbnRow()
    if target == OTHER_IDS_TARGET:
        return OtherIdRow(key=default_other_id_key(key))
    if target == AUTHORS_TARGET:
        delimiter = defaults.author_delimiter or defaults.delimiter
        return AuthorsRow(delimiter=delimiter, id_key=default_other_id_key(key))
    if target == KEYWORDS_TARGET:
        return KeywordsRow(delimiter=defaults.delimiter)
    if target == LABEL_TARGET:
        return LabelRow()
    if target in SCALAR_FIELDS:
        return ScalarRow.model_validate({"target": target})
    raise ValueError(f"{key!r} maps to unknown Record field {target!r}")


def row_with(row: RowMapping, options: Mapping[str, str]) -> RowMapping:
    return _ROW_ADAPTER.validate_python({**row.model_dump(), **options})


def make_row(suggest: Suggest, key: str, defaults: RowDefaults) -> RowMapping:
    return row_with(default_row(suggest.target, key, defaults), suggest.options)


_LABEL_SPELLINGS: dict[str, LabelValue] = {
    **dict.fromkeys(
        ("include", "included", "yes", "y", "1", "true", "relevant"), "include"
    ),
    **dict.fromkeys(
        ("exclude", "excluded", "no", "n", "0", "false", "irrelevant"), "exclude"
    ),
    **dict.fromkeys(("maybe", "unsure", "undecided", "?"), "maybe"),
    "": "unlabeled",
}
# ASReview writes -1 for records nobody has labeled yet.
_MINUS_ONE = "-1"

_ISSN_ISBN_SEPARATORS = re.compile(r"[\s;]+")
_ISSN_LENGTH = 8
_ISBN_LENGTHS = (10, 13)


def normalize_label(value: str, minus_one_unlabeled: bool = False) -> LabelValue:
    normalized = value.strip().lower()
    if minus_one_unlabeled and normalized == _MINUS_ONE:
        return "unlabeled"
    label = _LABEL_SPELLINGS.get(normalized)
    if label is None:
        logger.warning("Unknown label value %r", value)
        return "unknown"
    return label


def _issn_isbn_pieces(value: str, skip_qualifiers: bool) -> list[str]:
    """skip_qualifiers skips pieces like Scopus's "(ISSN)" / "(ISBN)"."""
    return [
        piece
        for piece in _ISSN_ISBN_SEPARATORS.split(value)
        if piece
        and not (skip_qualifiers and piece.startswith("(") and piece.endswith(")"))
    ]


def _classify_issn_isbn(row: IssnIsbnRow, value: str, skip: bool) -> dict[str, str]:
    """RIS keeps both in SN; auto tells them apart by length. First of each wins."""
    pieces = _issn_isbn_pieces(value, skip)
    if row.kind != "auto":
        return {row.kind: pieces[0]} if pieces else {}
    found: dict[str, str] = {}
    for piece in pieces:
        length = len(piece.replace("-", ""))
        if length in _ISBN_LENGTHS:
            found.setdefault("isbn", piece)
            continue
        if length != _ISSN_LENGTH:
            logger.warning("Value %r is neither an ISSN nor an ISBN", piece)
        found.setdefault("issn", piece)
    return found


def _split_list(value: str, delimiter: str) -> list[str]:
    return [piece.strip() for piece in value.split(delimiter) if piece.strip()]


def _parse_int_field(value: str, field_name: str) -> int | None:
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
) -> PartialDate | None:
    """Each part comes from the first row giving it; a year/month/day row beats a
    full date."""
    explicit: dict[str, int] = {}
    from_full: dict[str, int] = {}
    for key, row in mapping.rows_of(DateRow):
        value = (raw_fields.get(key) or "").strip()
        if not value:
            continue
        if row.part == "full":
            date = parse_date_string(value, row.order)
            for part in _DATE_PARTS if date is not None else ():
                if (number := getattr(date, part)) is not None:
                    from_full.setdefault(part, number)
            continue
        if row.part == "month":
            number = _parse_month(value)
        else:
            number = _parse_int_field(value, row.part)
        if number is not None:
            explicit.setdefault(row.part, number)
    parts = {**from_full, **explicit}
    return _build_partial_date(parts.get("year"), parts.get("month"), parts.get("day"))


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


def _continues_to_next(target: str, value: str, settings: ParseSettings) -> bool:
    return any(
        quirk.field == target and quirk.matches(value)
        for quirk in settings.continue_to_next
    )


def author_for_name(name: str, row: AuthorsRow, settings: ParseSettings) -> Author:
    if row.role == "full_name":
        return Author(full_name=name)
    return author_from_name(
        name,
        row.separator,
        settings.ambiguous_name_split,
        family_first=row.role == "last_first",
    )


def add_author_detail(author: Author, row: AuthorsRow, value: str) -> None:
    if row.role == "orcid":
        author.orcid = author.orcid or _ORCID_URL.sub("", value)
    elif row.role == "ids":
        author.other_ids.setdefault(row.id_key, value)
    elif row.role == "affiliations":
        author.affiliations.append(Affiliation(name=value))


def _split_positions(value: str | None, delimiter: str) -> list[str]:
    """Keeps empty pieces so positions line up across the columns."""
    if not value or not value.strip():
        return []
    return [piece.strip() for piece in value.split(delimiter)]


def _zip_authors(
    raw_fields: dict[str, str], mapping: FieldMapping, settings: ParseSettings
) -> list[Author]:
    """Authors zipped by position from parallel, delimited columns.

    The first non-empty name column sets the authors; with none, the first
    non-empty other column sets the count. A column with a different count is
    ignored with a warning.
    """
    columns = [
        (key, row, values)
        for key, row in mapping.rows_of(AuthorsRow)
        if (values := _split_positions(raw_fields.get(key), row.delimiter))
    ]
    names = next(((r, v) for _, r, v in columns if r.role in NAME_ROLES), None)
    details = [(k, r, v) for k, r, v in columns if r.role not in NAME_ROLES]
    if names is not None:
        name_row, name_values = names
        authors = [
            author_for_name(name, name_row, settings) if name else Author()
            for name in name_values
        ]
    else:
        authors = [Author() for _ in (details[0][2] if details else [])]
    for key, row, values in details:
        if len(values) != len(authors):
            logger.warning(
                "%r has %d entries for %d authors; ignoring it",
                key,
                len(values),
                len(authors),
            )
            continue
        for author, value in zip(authors, values, strict=True):
            if value:
                add_author_detail(author, row, value)
    return [a for a in authors if a.full_name or a.orcid or a.other_ids]


def apply_mapping(
    raw_fields: dict[str, str],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> Record:
    values: dict[str, Any] = {}
    other_ids: dict[str, str] = {}
    keywords: list[str] = []
    labels: list[Label] = []
    for key, row in mapping.rows.items():
        value = (raw_fields.get(key) or "").strip()
        if isinstance(row, LabelRow):
            labels.append(
                Label(
                    phase=row.phase,
                    screener=row.screener,
                    value=normalize_label(value, settings.minus_one_unlabeled),
                )
            )
            continue
        if not value:
            continue
        if isinstance(row, ScalarRow):
            if not _continues_to_next(row.target, value, settings):
                values.setdefault(row.target, value)
        elif isinstance(row, IssnIsbnRow):
            skip = settings.skip_issn_isbn_qualifiers
            for scalar, piece in _classify_issn_isbn(row, value, skip).items():
                values.setdefault(scalar, piece)
        elif isinstance(row, OtherIdRow):
            other_ids[row.key] = value
        elif isinstance(row, KeywordsRow):
            keywords.extend(
                row.prefix + keyword for keyword in _split_list(value, row.delimiter)
            )

    return Record(
        **values,
        pages=_parse_pages(raw_fields, mapping),
        other_ids=other_ids,
        authors=_zip_authors(raw_fields, mapping, settings),
        keywords=keywords,
        labels=labels,
        publication_date=_parse_publication_date(raw_fields, mapping),
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
    defaults: RowDefaults,
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
        rows[key] = make_row(suggest, key, defaults)
        match_kinds[key] = kind
    return FieldMapping(rows=rows, match_kinds=match_kinds)
