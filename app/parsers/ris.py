import logging
import re
from dataclasses import replace
from pathlib import Path

from app.models.record import Affiliation, Author
from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
)
from app.parsers.mapping import FieldMapping, apply_mapping, override_aliases
from app.parsers.mapping import suggest_mapping as _suggest_mapping
from app.parsers.quirks import NO_QUIRKS, ParseSettings

logger = logging.getLogger(__name__)

# Order matters for exclusive targets: DA carries the most date detail.
_SUGGESTION_ALIASES: dict[str, list[str]] = {
    "title": ["ti", "t1"],
    "authors": ["au", "a1", "ad"],
    "abstract": ["ab", "n2"],
    "journal": ["jo", "jf", "t2"],
    "issn_isbn": ["sn"],
    "volume": ["vl"],
    "issue": ["is"],
    "page_start": ["sp"],
    "page_end": ["ep"],
    "doi": ["do"],
    "publication_type": ["ty"],
    "language": ["la"],
    "publisher": ["pb"],
    "url": ["ur"],
    "notes": ["n1"],
    "keywords": ["kw"],
    "date": ["da", "py", "y1"],
    "other_ids": ["an"],
}

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9])  -(?: (?P<value>.*))?$")
_END_TAG = "ER"
_TYPE_TAG = "TY"
_AFFILIATION_TAGS = frozenset({"AD", "C1"})


def _authors_from_lines(
    lines: list[tuple[str, str]], author_tags: set[str]
) -> list[Author]:
    """An affiliation line belongs to the author directly above it.

    Any other tag in between ends the author, so a block of affiliations listed
    after all authors (as Scopus does) is not pinned on the last one.
    """
    authors: list[Author] = []
    current: Author | None = None
    for tag, value in lines:
        if tag not in author_tags:
            current = None
        elif tag in _AFFILIATION_TAGS:
            if current is not None and value:
                current.affiliations.append(Affiliation(name=value))
        elif value:
            current = Author(full_name=value)
            authors.append(current)
    return authors


def parse_ris_record(
    lines: list[tuple[str, str]],
    mapping: FieldMapping,
    settings: ParseSettings = NO_QUIRKS,
) -> ParsedRow:
    values: dict[str, list[str]] = {}
    for tag, value in lines:
        values.setdefault(tag, []).append(value)
    raw_fields = {t: "\n".join(v for v in vs if v) for t, vs in values.items()}
    record = apply_mapping(raw_fields, mapping, settings)
    author_tags = {k for k, t in mapping.targets.items() if t == "authors"}
    if author_tags:
        authors = _authors_from_lines(lines, author_tags)
        record = record.model_copy(update={"authors": authors})
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
            if not lines:
                skip(line_number, "text outside a record")
            else:
                tag, value = lines[-1]
                lines[-1] = (tag, value + "\n" + line.strip())
            continue

        tag = match["tag"]
        if tag == _END_TAG:
            if lines and all(t != _TYPE_TAG for t, _ in lines):
                skip(start_line, "record has no TY tag")
            elif lines:
                rows.append(parse_ris_record(lines, mapping, settings))
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
    tags: list[str], alias_overrides: dict[str, list[str]] | None = None
) -> FieldMapping:
    aliases = override_aliases(_SUGGESTION_ALIASES, alias_overrides or {})
    mapping = _suggest_mapping(tags, aliases, lenient=False)
    return replace(mapping, list_delimiter="\n")
