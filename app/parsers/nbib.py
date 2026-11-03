import logging
import re
from collections.abc import Mapping
from pathlib import Path

from app.models.record import Author
from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
)
from app.parsers.mapping import (
    LINE_DELIMITER,
    NAME_ROLES,
    AuthorsRow,
    FieldMapping,
    RowDefaults,
    Suggest,
    add_author_detail,
    apply_mapping,
    author_for_name,
    override_aliases,
)
from app.parsers.mapping import suggest_mapping as _suggest_mapping
from app.parsers.quirks import NO_QUIRKS, ParseSettings

logger = logging.getLogger(__name__)

_SCALARS = {
    "ti": "title",
    "ab": "abstract",
    "jt": "journal",
    "ta": "journal",
    "bti": "journal",
    "vi": "volume",
    "ip": "issue",
    "doi": "doi",
    "pmid": "pmid",
    "la": "language",
    "pt": "publication_type",
    "pb": "publisher",
}
# AU is not an alias: mapping it next to FAU would add every author twice.
# suggest_nbib_mapping falls back to it only when the file has no FAU.
_SUGGESTIONS: dict[str, Suggest] = {
    **{alias: Suggest(target) for alias, target in _SCALARS.items()},
    "fau": Suggest("authors"),
    "auid": Suggest("authors", {"role": "ids"}),
    "ad": Suggest("authors", {"role": "affiliations"}),
    "pg": Suggest("pages"),
    "ot": Suggest("keywords"),
    "mh": Suggest("keywords", {"prefix": "MeSH"}),
    "dp": Suggest("date"),
    "is": Suggest("issn_isbn", {"kind": "issn"}),
    "isbn": Suggest("issn_isbn", {"kind": "isbn"}),
    "pmc": Suggest("other_ids"),
    "mid": Suggest("other_ids"),
}
ROW_DEFAULTS = RowDefaults(delimiter=LINE_DELIMITER)
_AU_TAG = "AU"
_FAU_TAG = "FAU"

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9]{1,3}) *-(?: (?P<value>.*))?$")
_ID_TAGS = ("AID", "LID")
_DOI_SUFFIX = " [doi]"
_DOI_TAG = "DOI"
_REQUIRED_TAG = "PMID"
_ORCID_SCHEME = "ORCID"
_ORCID_URL = re.compile(r"^https?://orcid\.org/")
_EDITOR_TAGS = ("FED", "ED")


def _doi_from_id(value: str) -> str | None:
    stripped = value.strip()
    if not stripped.endswith(_DOI_SUFFIX):
        return None
    return stripped.removesuffix(_DOI_SUFFIX).strip() or None


def _add_auid(author: Author, row: AuthorsRow, value: str) -> None:
    """AUID values look like "ORCID: 0000-0001-8894-9875"; without a scheme the
    row's ID key is used."""
    scheme, colon, identifier = value.partition(":")
    if not colon:
        scheme, identifier = "", value
    scheme, identifier = scheme.strip(), identifier.strip()
    if not identifier:
        return
    if scheme.upper() == _ORCID_SCHEME:
        author.orcid = _ORCID_URL.sub("", identifier)
    else:
        author.other_ids[scheme.lower() or row.id_key] = identifier


def _authors_from_lines(
    lines: list[tuple[str, str]], rows: dict[str, AuthorsRow], settings: ParseSettings
) -> list[Author]:
    """Detail lines (AUID, AD) belong to the author or editor name line before them."""
    authors: list[Author] = []
    current: Author | None = None
    for tag, value in lines:
        row = rows.get(tag)
        if row is None:
            if tag in _EDITOR_TAGS:
                current = None
            continue
        if not value:
            continue
        if row.role in NAME_ROLES:
            current = author_for_name(value, row, settings)
            authors.append(current)
        elif current is not None and row.role == "ids":
            _add_auid(current, row, value)
        elif current is not None:
            add_author_detail(current, row, value)
    return authors


def parse_nbib_record(
    lines: list[tuple[str, str]],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> ParsedRow:
    values: dict[str, list[str]] = {}
    for tag, value in lines:
        values.setdefault(tag, []).append(value)
    raw_fields = {t: "\n".join(v for v in vs if v) for t, vs in values.items()}
    doi = next(
        (
            doi
            for tag in _ID_TAGS
            for value in values.get(tag, [])
            if (doi := _doi_from_id(value)) is not None
        ),
        None,
    )
    if doi is not None:
        raw_fields[_DOI_TAG] = doi
    record = apply_mapping(raw_fields, mapping, settings)
    author_rows = dict(mapping.rows_of(AuthorsRow))
    if author_rows:
        authors = _authors_from_lines(lines, author_rows, settings)
        record = record.model_copy(update={"authors": authors})
    return ParsedRow(record=record, raw_fields=raw_fields)


def parse_nbib_text(
    text: str, mapping: FieldMapping, settings: ParseSettings = NO_QUIRKS
) -> ParseResult:
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    def skip(line_number: int, reason: str) -> None:
        skipped.append(SkippedRow(line_number, reason))
        logger.warning("Skipping NBIB record at line %d: %s", line_number, reason)

    lines: list[tuple[str, str]] = []
    start_line = 0

    def finish_record() -> None:
        if not lines:
            return
        if all(tag != _REQUIRED_TAG for tag, _ in lines):
            skip(start_line, f"record has no {_REQUIRED_TAG} tag")
            return
        rows.append(parse_nbib_record(lines, mapping, settings))

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            finish_record()
            lines = []
            continue

        match = _TAG_LINE.match(line)
        if match is None:
            if not lines:
                skip(line_number, "text outside a record")
            else:
                tag, value = lines[-1]
                lines[-1] = (tag, value + " " + line.strip())
            continue

        if not lines:
            start_line = line_number
        lines.append((match["tag"], (match["value"] or "").strip()))

    finish_record()
    return ParseResult(rows=rows, skipped=skipped)


def parse_nbib_file(
    path: Path, mapping: FieldMapping, settings: ParseSettings = NO_QUIRKS
) -> ParseResult:
    return parse_nbib_text(decode_file(path), mapping, settings)


def read_nbib_tags(path: Path) -> FileSummary:
    summary = SummaryBuilder()
    for line in decode_file(path).splitlines():
        if not line.strip():
            summary.end_record()
            continue
        match = _TAG_LINE.match(line)
        if match is None:
            continue
        value = match["value"] or ""
        summary.add(match["tag"], value)
        if match["tag"] in _ID_TAGS and (doi := _doi_from_id(value)) is not None:
            summary.add(_DOI_TAG, doi)
    return summary.build()


def suggest_nbib_mapping(
    tags: list[str],
    overrides: Mapping[str, Suggest] | None = None,
    defaults: RowDefaults = ROW_DEFAULTS,
) -> FieldMapping:
    suggestions = override_aliases(_SUGGESTIONS, overrides or {})
    if _FAU_TAG not in tags:
        suggestions[_AU_TAG.lower()] = Suggest("authors")
    return _suggest_mapping(tags, suggestions, defaults, lenient=False)
