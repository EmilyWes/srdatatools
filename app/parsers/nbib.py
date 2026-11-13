import logging
import re
from collections.abc import Mapping
from functools import partial
from pathlib import Path

from app.parsers.authors import AuthorIds, author_id
from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
    parse_or_skip,
)
from app.parsers.mapping import (
    AuthorsRow,
    FieldMapping,
    Suggest,
    apply_line_mapping,
    join_tag_lines,
    override_aliases,
)
from app.parsers.mapping import suggest_mapping as _suggest_mapping
from app.parsers.quirks import NO_QUIRKS, ParseSettings

logger = logging.getLogger(__name__)

_SCALARS = {
    "ti": "title",
    "tt": "title",
    "ab": "abstract",
    "jt": "journal",
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
    "pmc": Suggest("other_ids", {"key": "pmcid"}),
    "mid": Suggest("other_ids"),
}
_AU_TAG = "AU"
_FAU_TAG = "FAU"

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9]{1,3}) *-(?: (?P<value>.*))?$")
_ID_TAGS = ("AID", "LID")
_DOI_SUFFIX = " [doi]"
_DOI_TAG = "DOI"
_REQUIRED_TAG = "PMID"
_EDITOR_TAGS = ("FED", "ED")


def _doi_from_id(value: str) -> str | None:
    stripped = value.strip()
    if not stripped.endswith(_DOI_SUFFIX):
        return None
    return stripped.removesuffix(_DOI_SUFFIX).strip() or None


def _auid(row: AuthorsRow, value: str) -> str | None:
    """AUID values look like "ORCID: 0000-0001-8894-9875"; the scheme is the key,
    without one the row's ID key is used."""
    scheme, colon, identifier = value.partition(":")
    if not colon:
        scheme, identifier = "", value
    if not identifier.strip():
        return None
    return author_id(scheme.strip().lower() or row.id_key, identifier)


def _author_lines(
    lines: list[tuple[str, str]], rows: dict[str, AuthorsRow]
) -> tuple[list[tuple[str, str]], AuthorIds]:
    """AUID and AD lines belong to the author or editor name line before them;
    an editor's, or one before the first author, is left out."""
    kept: list[tuple[str, str]] = []
    slots: AuthorIds = []
    current: list[str] | None = None
    for tag, value in lines:
        row = rows.get(tag)
        if row is None:
            if tag in _EDITOR_TAGS:
                current = None
            continue
        if not value:
            continue
        if row.role == "names":
            current = []
            slots.append(current)
            kept.append((tag, value))
        elif current is None:
            continue
        elif row.role == "affiliations":
            kept.append((tag, value))
        elif (auid := _auid(row, value)) is not None:
            current.append(auid)
    return kept, slots


def parse_nbib_record(
    lines: list[tuple[str, str]],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> ParsedRow:
    raw_fields = join_tag_lines(lines)
    doi = next(
        (
            doi
            for tag in _ID_TAGS
            for value in raw_fields.get(tag, "").splitlines()
            if (doi := _doi_from_id(value)) is not None
        ),
        None,
    )
    if doi is not None:
        raw_fields[_DOI_TAG] = doi
    record = apply_line_mapping(lines, raw_fields, mapping, settings, _author_lines)
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
        parse_or_skip(
            rows,
            skipped,
            start_line,
            partial(parse_nbib_record, lines, mapping, settings),
        )

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
    ignored_keys: frozenset[str] = frozenset(),
) -> FieldMapping:
    suggestions = override_aliases(_SUGGESTIONS, overrides or {})
    if _FAU_TAG not in tags:
        suggestions[_AU_TAG.lower()] = Suggest("authors")
    return _suggest_mapping(tags, suggestions, lenient=False, ignored_keys=ignored_keys)
