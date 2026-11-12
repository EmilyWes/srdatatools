import re
import string
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from app.cleaning.options import CleaningOptions
from app.models.record import Record
from app.parsers.authors import (
    AUTHOR_JOINER,
    AuthorIds,
    author_id,
    format_author_ids,
    merge_author_ids,
    parse_author_ids,
    parse_unsplit_author_ids,
)
from app.parsers.mapping import (
    ISBN_LENGTHS,
    ISSN_ISBN_TOKEN,
    ISSN_LENGTH,
    LINE_DELIMITER,
    SCALAR_FIELDS,
    AuthorsRow,
    FieldMapping,
    ScalarRow,
    ordered_mapping,
    parse_unsplit_keywords,
    tag_keyword,
)

SCOPUS_AUTHOR_ID_KEY = "scopus_author_id"
# Comma is left out: it also separates last and first names.
SEPARATOR_CANDIDATES = (AUTHOR_JOINER, ";", "\n", " and ")

_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")
_TRAILING_ET_AL = re.compile(r"[\s,;|]*\bet al\.$")
_TRAILING_ID = re.compile(r"\s*\((?P<id>\d+)\)\s*$")
_TRAILING_BRACKETS = re.compile(r"\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$")
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DIGITS = re.compile(r"\d+")
_TRAILING_NON_NAME = ".,;:…" + string.whitespace
# Only the plain form: ;volume(issue):pages followed by a full stop.
_CITATION_PARTS = re.compile(
    r";(?P<volume>\d+)\((?P<issue>\d+)\):(?P<pages>\d+(?:-\d+)?)\.(?:\s|$)"
)
# Current exports link .../pages/publications/<n>; older ones .../record.uri?eid=...
_SCOPUS_URL_EID = re.compile(
    r"scopus\.com/(?:pages/publications/|inward/record\.uri\?.*?\beid=2-s2\.0-)(\d+)"
)
_EID_PREFIX = "2-s2.0-"
_ISSN_ISBN_JOINER = "; "
_AUTHOR_TEXT_FIELDS = {"names": "author_names", "affiliations": "author_affiliations"}
_EMPTY_VALUE_FIELDS = (*sorted(SCALAR_FIELDS), *_AUTHOR_TEXT_FIELDS.values())
_RIS_NOTES_TAG = "N1"
_RIS_NOTE_IDS = {"EID: ": "eid"}
_RIS_NOTE_FIELDS = {"Conference name: ": "conference_name"}
_BIBTEX_URL_KEY = "url"
_CITATION_KEY = "Citation"


@dataclass(frozen=True)
class CleaningContext:
    """What a record's source file adds: its raw fields and mapping, and the
    author separators chosen or sniffed for that file."""

    raw_fields: dict[str, str] = field(default_factory=dict)
    mapping: FieldMapping = field(default_factory=FieldMapping)
    use_first: tuple[str, ...] = ()
    names_separator: str | None = None
    affiliations_separator: str | None = None
    ids_separator: str | None = None
    keywords_separator: str | None = None


Step = Callable[[Record, CleaningContext, CleaningOptions], Record]


def sniff_separator(values: Iterable[str | None]) -> str | None:
    """The candidate found in the most values; earlier candidates win ties."""
    counts = dict.fromkeys(SEPARATOR_CANDIDATES, 0)
    for value in values:
        for candidate in SEPARATOR_CANDIDATES:
            if value and candidate in value:
                counts[candidate] += 1
    best = max(counts, key=lambda candidate: counts[candidate])
    return best if counts[best] else None


def file_separators(
    records: Sequence[Record], options: CleaningOptions
) -> tuple[str | None, str | None, str | None, str | None]:
    """The names, affiliations, ids and keywords separators for one source file's
    records: the chosen ones, else sniffed from the records."""
    names = options.names_separator or sniff_separator(
        record.author_names for record in records
    )
    affiliations = options.affiliations_separator or sniff_separator(
        record.author_affiliations for record in records
    )
    ids = options.ids_separator or sniff_separator(
        value
        for record in records
        for _, value in parse_unsplit_author_ids(record.author_ids)
    )
    keywords = options.keywords_separator or sniff_separator(
        unsplit[1]
        for record in records
        for keyword in record.keywords
        if (unsplit := parse_unsplit_keywords(keyword)) is not None
    )
    return names, affiliations, ids, keywords


def expand_page_range(pages: str) -> str:
    """PubMed drops the leading digits the end page shares with the start: 521-2."""
    match = _PAGE_RANGE.match(pages)
    if match is None or int(match["end"]) >= int(match["start"]):
        return pages
    start, end = match["start"], match["end"]
    return f"{start}-{start[: -len(end)]}{end}"


def _counts_as_empty(value: str, options: CleaningOptions) -> bool:
    empty = {v.strip().lower() for v in options.empty_values if v.strip()}
    return value.strip().lower() in empty


def _raw_value(key: str, context: CleaningContext) -> str:
    value = (context.raw_fields.get(key) or "").strip()
    if isinstance(context.mapping.rows[key], AuthorsRow):
        return AUTHOR_JOINER.join(line for line in value.splitlines() if line)
    return value


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
        value = _raw_value(key, context) if maps_here else ""
        if value and not _counts_as_empty(value, options):
            return value
    return None


def clear_empty_values(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    update: dict[str, str | None] = {}
    for name in _EMPTY_VALUE_FIELDS:
        value: str | None = getattr(record, name)
        if value is not None and _counts_as_empty(value, options):
            refill = (
                _refill(name, context, options) if options.refill_from_raw else None
            )
            update[name] = refill
    return record.model_copy(update=update)


def _split(value: str | None, separator: str | None) -> str | None:
    if not value or not separator or AUTHOR_JOINER in value:
        return value
    pieces = (piece.strip() for piece in value.split(separator))
    return AUTHOR_JOINER.join(piece for piece in pieces if piece) or None


def _split_ids(value: str | None, separator: str | None) -> str | None:
    """Each "key:[value]" column is split by position and merged per author;
    without a separator its value is one author's id."""
    columns = parse_unsplit_author_ids(value)
    if not columns:
        return value
    slots: AuthorIds = []
    for key, ids in columns:
        split = ids.split(separator) if separator else [ids]
        pieces = (piece.strip() for piece in split)
        new = [[author_id(key, piece)] if piece else [] for piece in pieces]
        slots = merge_author_ids(slots, new, key)
    return format_author_ids(slots)


def split_authors(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    return record.model_copy(
        update={
            "author_names": _split(record.author_names, context.names_separator),
            "author_affiliations": _split(
                record.author_affiliations, context.affiliations_separator
            ),
            "author_ids": _split_ids(record.author_ids, context.ids_separator),
        }
    )


def split_keywords(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Without a separator an unsplit value is one keyword."""
    separator = context.keywords_separator
    keywords: list[str] = []
    for keyword in record.keywords:
        unsplit = parse_unsplit_keywords(keyword)
        if unsplit is None:
            keywords.append(keyword)
            continue
        prefix, value = unsplit
        pieces = value.split(separator) if separator else [value]
        keywords.extend(tag_keyword(prefix, p.strip()) for p in pieces if p.strip())
    return record.model_copy(update={"keywords": keywords})


def id_from_name(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Ids that can't be matched to the authors by position are dropped, but the
    names are still cleaned."""
    if not record.author_names:
        return record
    names = record.author_names.split(AUTHOR_JOINER)
    matches = [_TRAILING_ID.search(name) for name in names]
    if not any(matches):
        return record
    new_ids = [[author_id(SCOPUS_AUTHOR_ID_KEY, m["id"])] if m else [] for m in matches]
    merged = merge_author_ids(
        parse_author_ids(record.author_ids), new_ids, "author names"
    )
    cleaned = AUTHOR_JOINER.join(_TRAILING_ID.sub("", name) for name in names)
    return record.model_copy(
        update={"author_names": cleaned, "author_ids": format_author_ids(merged)}
    )


def strip_author_extras(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.author_names:
        return record
    names = record.author_names.split(AUTHOR_JOINER)
    cleaned = AUTHOR_JOINER.join(_TRAILING_BRACKETS.sub("", name) for name in names)
    return record.model_copy(update={"author_names": cleaned})


def strip_affiliation_start(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """Only strips when the text before the separator starts with the last name of
    the author at the same position, so cleaning again strips nothing more. Such
    an affiliation without the separator is only a name, so it is dropped."""
    separator = options.affiliation_start
    if not record.author_affiliations or not record.author_names or not separator:
        return record
    names = record.author_names.split(AUTHOR_JOINER)
    kept = []
    for index, affiliation in enumerate(
        record.author_affiliations.split(AUTHOR_JOINER)
    ):
        last_name = names[index].split(",")[0].strip() if index < len(names) else ""
        lead, found, rest = affiliation.partition(separator)
        if not (last_name and lead.lower().startswith(last_name.lower())):
            kept.append(affiliation)
        elif found and rest.strip():
            kept.append(rest.strip())
    return record.model_copy(
        update={"author_affiliations": AUTHOR_JOINER.join(kept) or None}
    )


def drop_et_al(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.author_names:
        return record
    names = _TRAILING_ET_AL.sub("", record.author_names)
    return record.model_copy(update={"author_names": names or None})


def drop_trailing(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    if not record.author_names:
        return record
    names = record.author_names.rstrip(_TRAILING_NON_NAME)
    return record.model_copy(update={"author_names": names or None})


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
    value: str | None, lengths: tuple[int, ...], options: CleaningOptions
) -> str | None:
    if not value:
        return value
    tokens = [
        token
        for token in ISSN_ISBN_TOKEN.finditer(value)
        if len(token["id"].replace("-", "")) in lengths
    ]
    if not tokens:
        return value
    if options.only_one:
        tokens = [_preferred_token(tokens, options.preferred_qualifier)]
    return _ISSN_ISBN_JOINER.join(
        token["id"] if options.strip_extras else token[0] for token in tokens
    )


def clean_issn_isbn(
    record: Record, context: CleaningContext, options: CleaningOptions
) -> Record:
    """The issn field keeps ISSN-length numbers and the isbn field ISBN-length
    ones; a value with none of them is kept as it is."""
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
        (options.strip_doi, "Strip DOI", strip_doi),
        (options.strip_pmid, "Strip PMID", strip_pmid),
        (options.strip_extras or options.only_one, "ISSN/ISBN", clean_issn_isbn),
        (options.first_publication_type, "First pub. type", first_publication_type),
        (options.ris_notes, "RIS notes", ris_notes),
        (options.eid_from_url, "EID from URL", eid_from_url),
        (options.citation_parts, "Values from Citation", citation_parts),
        (options.pages_set, "Pages set", pages_set),
    ]


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
