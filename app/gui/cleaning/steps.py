import logging
import re
import string
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.gui.cleaning.options import CleaningOptions, DateOrder
from app.gui.importing.mapping import (
    ISBN_LENGTHS,
    ISSN_ISBN_TOKEN,
    ISSN_LENGTH,
    LINE_DELIMITER,
    AuthorsRow,
    FieldMapping,
    ScalarRow,
    ordered_mapping,
)
from app.helpers.authors import AuthorIds, clean_author_id, merge_author_ids
from app.helpers.format import STANDARD_PUBLICATION_TYPE
from app.helpers.functions import sniff_separator
from app.helpers.record_fields import SCALAR_FIELDS
from app.models.record import PartialDate, Record

logger = logging.getLogger(__name__)

SCOPUS_AUTHOR_ID_KEY = "scopus_author_id"
# Comma is left out: it also separates last and first names, and the parts of an
# affiliation.
SEPARATOR_CANDIDATES = ("|", ";", "\n", " and ")
# Comma last, so it loses ties to a keyword that only contains one.
COMMA_SEPARATOR_CANDIDATES = (*SEPARATOR_CANDIDATES, ",")

_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")
_TRAILING_ET_AL = re.compile(r"[\s,;|]*\bet al\.$")
_TRAILING_ID = re.compile(r"\s*\((?P<id>\d+)\)\s*$")
_TRAILING_BRACKETS = re.compile(r"\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$")
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DIGITS = re.compile(r"\d+")
_TRAILING_NON_NAME = ".,;:…" + string.whitespace
_ENDS_IN_WORD = re.compile(r"[^\W\d_]{3}$")
_INITIALS = re.compile(r"(?:[\s.\-]+[^\W\d_]{1,3})*\.?")
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
# Only the plain form: ;volume(issue):pages followed by a full stop.
_CITATION_PARTS = re.compile(
    r";(?P<volume>\d+)\((?P<issue>\d+)\):(?P<pages>\d+(?:-\d+)?)\.(?:\s|$)"
)
# Current exports link .../pages/publications/<n>; older ones .../record.uri?eid=...
_SCOPUS_URL_EID = re.compile(
    r"scopus\.com/(?:pages/publications/|inward/record\.uri\?.*?\beid=2-s2\.0-)(\d+)"
)
_EID_PREFIX = "2-s2.0-"
_AUTHOR_TEXT_FIELDS = {"names": "author_names", "affiliations": "author_affiliations"}
_RIS_NOTES_TAG = "N1"
_RIS_NOTE_IDS = {"EID: ": "eid"}
_RIS_NOTE_FIELDS = {"Conference name: ": "conference_name"}
_BIBTEX_URL_KEY = "url"
_CITATION_KEY = "Citation"


@dataclass(frozen=True)
class CleaningContext:
    """What a record's source file adds: its raw fields and mapping, whether its
    values are split (a table format's are stored as they come), and the
    separators chosen or sniffed for that file."""

    raw_fields: dict[str, str] = field(default_factory=dict)
    split: bool = False
    mapping: FieldMapping = field(default_factory=FieldMapping)
    use_first: tuple[str, ...] = ()
    names_separator: str | None = None
    affiliations_separator: str | None = None
    ids_separator: str | None = None
    keywords_separator: str | None = None


Step = Callable[[Record, CleaningContext, CleaningOptions], Record]


def get_separators(
    records: Sequence[Record], options: CleaningOptions
) -> tuple[str | None, str | None, str | None, str | None]:
    """The names, affiliations, ids and keywords separators for one source file's
    records: the chosen ones, else sniffed from the records."""
    names = options.names_separator or sniff_separator(
        (name for record in records for name in record.author_names),
        SEPARATOR_CANDIDATES,
    )
    affiliations = options.affiliations_separator or sniff_separator(
        (value for record in records for value in record.author_affiliations),
        SEPARATOR_CANDIDATES,
    )
    ids = options.ids_separator or sniff_separator(
        (
            value
            for record in records
            for values in record.author_ids.values()
            for value in values
        ),
        COMMA_SEPARATOR_CANDIDATES,
    )
    keywords = options.keywords_separator or sniff_separator(
        (
            keyword
            for record in records
            for values in record.keywords.values()
            for keyword in values
        ),
        COMMA_SEPARATOR_CANDIDATES,
    )
    return names, affiliations, ids, keywords


def expand_page_range(pages: str) -> str:
    """PubMed drops the leading digits the end page shares with the start: 521-2."""
    match = _PAGE_RANGE.match(pages)
    if match is None or int(match["end"]) >= int(match["start"]):
        return pages
    start = match["start"]
    end = start[: -len(match["end"])] + match["end"]
    if int(end) < int(start):
        return pages
    return f"{start}-{end}"


def _counts_as_empty(value: str, options: CleaningOptions) -> bool:
    empty = {v.strip().lower() for v in options.empty_values if v.strip()}
    return value.strip().lower() in empty


def _refill(
    target: str, context: CleaningContext, options: CleaningOptions
) -> str | None:
    mapping = ordered_mapping(context.mapping, context.use_first)
    for key, row in mapping.rows.items():
        if isinstance(row, ScalarRow):
            maps_here = row.target == target
        elif isinstance(row, AuthorsRow):
            maps_here = _AUTHOR_TEXT_FIELDS.get(row.role) == target
        else:
            maps_here = False
        value = (context.raw_fields.get(key) or "").strip() if maps_here else ""
        if value and not _counts_as_empty(value, options):
            return value
    return None


def clear_empty_values(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Authors count as empty when there is one, and it counts as empty; refilled
    from the raw fields they are a line each."""
    update: dict[str, str | list[str] | None] = {}
    for name in sorted(SCALAR_FIELDS):
        value: str | None = getattr(record, name)
        if value is not None and _counts_as_empty(value, options):
            refill = (
                _refill(name, context, options) if options.refill_from_raw else None
            )
            update[name] = refill
    for name in _AUTHOR_TEXT_FIELDS.values():
        values: list[str] = getattr(record, name)
        if len(values) == 1 and _counts_as_empty(values[0], options):
            refill = (
                _refill(name, context, options) if options.refill_from_raw else None
            )
            lines = (refill or "").splitlines()
            update[name] = [line.strip() for line in lines if line.strip()]
    return record.model_copy(update=update)


def _split_values(values: list[str], separator: str | None) -> list[str]:
    """Empty pieces are kept so positions keep matching the authors; splitting
    again on the same separator changes nothing."""
    if not separator:
        return values
    pieces = [piece.strip() for value in values for piece in value.split(separator)]
    return pieces if any(pieces) else []


def split_authors(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Each ID key is split on its own; without a separator a value is one
    author's ID."""
    if not context.split:
        return record
    ids: AuthorIds = {}
    for key, values in record.author_ids.items():
        pieces = _split_values(values, context.ids_separator)
        if any(pieces):
            ids[key] = [clean_author_id(piece) for piece in pieces]
    return record.model_copy(
        update={
            "author_names": _split_values(record.author_names, context.names_separator),
            "author_affiliations": _split_values(
                record.author_affiliations, context.affiliations_separator
            ),
            "author_ids": ids,
        }
    )


def split_keywords(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Without a separator a value is one keyword."""
    if not context.split:
        return record
    keywords: dict[str, list[str]] = {}
    for prefix, values in record.keywords.items():
        pieces = [p for p in _split_values(values, context.keywords_separator) if p]
        if pieces:
            keywords[prefix] = pieces
    return record.model_copy(update={"keywords": keywords})


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


def _parse_date_string(value: str, order: DateOrder = "eu") -> PartialDate | None:
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


def _format_date(date: PartialDate) -> str:
    parts = (
        (date.year, 4),
        (date.month, 2),
        (date.day, 2),
    )
    return "/".join("" if n is None else f"{n:0{width}d}" for n, width in parts)


def clean_date(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.publication_date:
        return record
    date = _parse_date_string(record.publication_date, options.date_order)
    if date is None:
        return record
    return record.model_copy(update={"publication_date": _format_date(date)})


def id_from_name(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Ids that can't be matched to the authors by position are dropped, but the
    names are still cleaned."""
    names = record.author_names
    matches = [_TRAILING_ID.search(name) for name in names]
    if not any(matches):
        return record
    new_ids = [match["id"] if match else "" for match in matches]
    return record.model_copy(
        update={
            "author_names": [_TRAILING_ID.sub("", name) for name in names],
            "author_ids": merge_author_ids(
                record.author_ids, SCOPUS_AUTHOR_ID_KEY, new_ids
            ),
        }
    )


def strip_author_extras(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    cleaned = [_TRAILING_BRACKETS.sub("", name) for name in record.author_names]
    return record.model_copy(update={"author_names": cleaned})


def strip_affiliation_start(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Only strips when the text before the separator is the last name of the
    author at the same position plus initials, so cleaning again strips nothing
    more and "Steinmann Institut" is kept for author Stein. Such an affiliation
    without the separator is only a name, so it is dropped."""
    separator = options.affiliation_start
    if not record.author_affiliations or not record.author_names or not separator:
        return record
    names = record.author_names
    kept = []
    for index, affiliation in enumerate(record.author_affiliations):
        last_name = names[index].split(",")[0].strip() if index < len(names) else ""
        lead, found, rest = affiliation.partition(separator)
        is_name = (
            last_name
            and lead.lower().startswith(last_name.lower())
            and _INITIALS.fullmatch(lead[len(last_name) :])
        )
        if not is_name:
            kept.append(affiliation)
        elif found and rest.strip():
            kept.append(rest.strip())
    return record.model_copy(update={"author_affiliations": kept})


def drop_et_al(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """In the last name, so also in names not split yet; a split-off "et al." is
    dropped as a whole."""
    if not record.author_names:
        return record
    *names, last = record.author_names
    last = _TRAILING_ET_AL.sub("", last)
    return record.model_copy(update={"author_names": [*names, last] if last else names})


def drop_trailing(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """In the last name. A full stop is kept unless it follows a word of three or
    more letters, so an initial's (J.) or an abbreviated name's (Yu.) stays."""
    if not record.author_names:
        return record
    *names, last = record.author_names
    stripped = last.rstrip(_TRAILING_NON_NAME)
    if last[len(stripped) :].startswith(".") and not _ENDS_IN_WORD.search(stripped):
        stripped += "."
    if not names and not stripped:
        return record.model_copy(update={"author_names": []})
    return record.model_copy(update={"author_names": [*names, stripped]})


def _keep_match(record: Record, name: str, pattern: re.Pattern[str]) -> Record:
    value: str | None = getattr(record, name)
    match = pattern.search(value or "")
    if match is None:
        return record
    return record.model_copy(update={name: match[0]})


def strip_doi(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    return _keep_match(record, "doi", _DOI)


def strip_pmid(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    return _keep_match(record, "pmid", _DIGITS)


def _preferred_token(tokens: list[re.Match[str]], preferred: str) -> re.Match[str]:
    wanted = preferred.strip().lower()
    return next(
        (t for t in tokens if wanted and (t["qualifier"] or "").lower() == wanted),
        tokens[0],
    )


def _clean_issn_isbn(
    values: list[str], lengths: tuple[int, ...], options: CleaningOptions
) -> list[str]:
    tokens = [
        token
        for value in values
        for token in ISSN_ISBN_TOKEN.finditer(value)
        if len(token["id"].replace("-", "")) in lengths
    ]
    if not tokens:
        return values
    if options.only_one:
        tokens = [_preferred_token(tokens, options.preferred_qualifier)]
    return [token["id"] if options.strip_extras else token[0] for token in tokens]


def clean_issn_isbn(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """The issn field keeps ISSN-length numbers and the isbn field ISBN-length
    ones; values with none of them are kept as they are."""
    return record.model_copy(
        update={
            "issn": _clean_issn_isbn(record.issn, (ISSN_LENGTH,), options),
            "isbn": _clean_issn_isbn(record.isbn, ISBN_LENGTHS, options),
        }
    )


def first_publication_type(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.publication_type:
        return record
    first = record.publication_type.split(LINE_DELIMITER)[0].strip()
    return record.model_copy(update={"publication_type": first})


def standardize_publication_type(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.publication_type:
        return record
    key = record.publication_type.strip().lower()
    standard = STANDARD_PUBLICATION_TYPE.get(key, record.publication_type)
    return record.model_copy(update={"publication_type": standard})


def ris_notes(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Scopus packs labelled values into N1 lines, e.g. "EID: 2-s2.0-105040180364".
    An other ID is always set; a field is only filled when it is empty."""
    lines = context.raw_fields.get(_RIS_NOTES_TAG, "").splitlines()

    def note(prefix: str) -> str | None:
        return next(
            (
                line.removeprefix(prefix).strip() or None
                for line in lines
                if line.startswith(prefix)
            ),
            None,
        )

    other_ids = dict(record.other_ids)
    for prefix, key in _RIS_NOTE_IDS.items():
        value = note(prefix)
        if value is not None:
            other_ids[key] = value
    update: dict[str, object] = {"other_ids": other_ids}
    for prefix, name in _RIS_NOTE_FIELDS.items():
        if getattr(record, name) is None:
            update[name] = note(prefix)
    return record.model_copy(update=update)


def eid_from_url(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    match = _SCOPUS_URL_EID.search(context.raw_fields.get(_BIBTEX_URL_KEY, ""))
    if match is None:
        return record
    other_ids = {**record.other_ids, "eid": _EID_PREFIX + match[1]}
    return record.model_copy(update={"other_ids": other_ids})


def citation_parts(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """PubMed CSV packs volume, issue and pages into one column, e.g.
    "Nature. 2023 Aug;620(7974):589-594. doi: ...". Only fills empty fields.
    """
    match = _CITATION_PARTS.search(context.raw_fields.get(_CITATION_KEY, ""))
    if match is None:
        return record
    update = {
        name: match[name]
        for name in ("volume", "issue", "pages")
        if not getattr(record, name)
    }
    return record.model_copy(update=update)


def pages_set(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.pages:
        return record
    return record.model_copy(update={"pages": expand_page_range(record.pages)})


def _steps(options: CleaningOptions) -> list[tuple[bool, str, Step]]:
    """In this order: author steps after splitting, ID from name before Drop
    trailing (which would leave its ")" alone), Pages set last so it also
    expands pages from Citation."""
    split = options.split_authors
    return [
        (bool(options.empty_values), "Empty values", clear_empty_values),
        (split, "Split authors", split_authors),
        (split and options.id_from_name, "Scopus ID from name", id_from_name),
        (
            split and options.author_strip_extras,
            "Author extras",
            strip_author_extras,
        ),
        (
            split and bool(options.affiliation_start),
            "Affiliation start",
            strip_affiliation_start,
        ),
        (options.drop_et_al, 'Drop "et al."', drop_et_al),
        (options.drop_trailing, "Drop trailing", drop_trailing),
        (options.split_keywords, "Split keywords", split_keywords),
        (options.clean_dates, "Clean up dates", clean_date),
        (options.strip_doi, "Strip DOI", strip_doi),
        (options.strip_pmid, "Strip PMID", strip_pmid),
        (options.strip_extras or options.only_one, "ISSN/ISBN", clean_issn_isbn),
        (options.first_publication_type, "First pub. type", first_publication_type),
        (
            options.standardize_publication_type,
            "Standardize pub. type",
            standardize_publication_type,
        ),
        (options.ris_notes, "RIS notes", ris_notes),
        (options.eid_from_url, "EID from URL", eid_from_url),
        (options.citation_parts, "Values from Citation", citation_parts),
        (options.pages_set, "Pages set", pages_set),
    ]


STEP_NAMES = [name for _, name, _ in _steps(CleaningOptions())]


def clean_record(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> tuple[Record, list[str]]:
    """The cleaned record and the names of the steps that changed it."""
    changed: list[str] = []
    for on, name, step in _steps(options):
        if not on:
            continue
        cleaned = step(record, context, options)
        if cleaned != record:
            changed.append(name)
        record = cleaned
    return record, changed
