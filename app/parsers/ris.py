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
    RowDefaults,
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
    "t1": "title",
    "ab": "abstract",
    "n2": "abstract",
    "jo": "journal",
    "jf": "journal",
    "t2": "journal",
    "vl": "volume",
    "is": "issue",
    "do": "doi",
    "ty": "publication_type",
    "la": "language",
    "pb": "publisher",
    "ur": "url",
    "n1": "notes",
}
_SUGGESTIONS: dict[str, Suggest] = {
    **{alias: Suggest(target) for alias, target in _SCALARS.items()},
    "au": Suggest("authors"),
    "a1": Suggest("authors"),
    "ad": Suggest("authors", {"role": "affiliations"}),
    "sn": Suggest("issn_isbn"),
    "sp": Suggest("pages", {"part": "start"}),
    "ep": Suggest("pages", {"part": "end"}),
    "kw": Suggest("keywords"),
    "da": Suggest("date"),
    "py": Suggest("date"),
    "y1": Suggest("date"),
    "an": Suggest("other_ids"),
}
ROW_DEFAULTS = RowDefaults()

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9])  -(?: (?P<value>.*))?$")
_END_TAG = "ER"
_TYPE_TAG = "TY"


def _author_lines(
    lines: list[tuple[str, str]], rows: dict[str, AuthorsRow]
) -> tuple[list[tuple[str, str]], AuthorIds]:
    """An ID line belongs to the author directly above it; an affiliation line may
    sit in between, any other tag ends the author. Every name and affiliation
    line is kept: Scopus lists the affiliations after all authors."""
    kept: list[tuple[str, str]] = []
    slots: AuthorIds = []
    current: list[str] | None = None
    for tag, value in lines:
        row = rows.get(tag)
        if row is None:
            current = None
        elif not value:
            continue
        elif row.role == "names":
            current = []
            slots.append(current)
            kept.append((tag, value))
        elif row.role == "affiliations":
            kept.append((tag, value))
        elif current is not None:
            current.append(author_id(row.id_key, value))
    return kept, slots


def parse_ris_record(
    lines: list[tuple[str, str]],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> ParsedRow:
    raw_fields = join_tag_lines(lines)
    record = apply_line_mapping(lines, raw_fields, mapping, settings, _author_lines)
    return ParsedRow(record=record, raw_fields=raw_fields)


def parse_ris_text(
    text: str, mapping: FieldMapping, settings: ParseSettings = NO_QUIRKS
) -> ParseResult:
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    def skip(line_number: int, reason: str) -> None:
        skipped.append(SkippedRow(line_number, reason))
        logger.warning("Skipping RIS record at line %d: %s", line_number, reason)

    lines: list[tuple[str, str]] = []
    start_line = 0

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _TAG_LINE.match(line)
        if match is None:
            if not line.strip():
                continue
            # ASReview numbers each record ("1.") between ER and the next TY.
            if not lines:
                logger.debug(
                    "Ignoring RIS text outside a record at line %d", line_number
                )
            else:
                tag, value = lines[-1]
                lines[-1] = (tag, value + "\n" + line.strip())
            continue

        tag = match["tag"]
        if tag == _END_TAG:
            if lines and all(t != _TYPE_TAG for t, _ in lines):
                skip(start_line, "record has no TY tag")
            elif lines:
                parse_or_skip(
                    rows,
                    skipped,
                    start_line,
                    partial(parse_ris_record, lines, mapping, settings),
                )
            lines = []
            continue

        if not lines:
            start_line = line_number
        lines.append((tag, (match["value"] or "").strip()))

    if lines:
        skip(start_line, "record is missing its ER terminator")

    return ParseResult(rows=rows, skipped=skipped)


def parse_ris_file(
    path: Path, mapping: FieldMapping, settings: ParseSettings = NO_QUIRKS
) -> ParseResult:
    return parse_ris_text(decode_file(path), mapping, settings)


def read_ris_tags(path: Path) -> FileSummary:
    summary = SummaryBuilder()
    for line in decode_file(path).splitlines():
        match = _TAG_LINE.match(line)
        if match is None:
            continue
        if match["tag"] == _END_TAG:
            summary.end_record()
        else:
            summary.add(match["tag"], match["value"] or "")
    return summary.build()


def suggest_ris_mapping(
    tags: list[str],
    overrides: Mapping[str, Suggest] | None = None,
    defaults: RowDefaults = ROW_DEFAULTS,
) -> FieldMapping:
    suggestions = override_aliases(_SUGGESTIONS, overrides or {})
    return _suggest_mapping(tags, suggestions, defaults, lenient=False)
