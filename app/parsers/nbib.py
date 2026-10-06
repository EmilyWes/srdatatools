import logging
import re
from dataclasses import replace
from pathlib import Path

from app.parsers.common import ParsedRow, ParseResult, SkippedRow, decode_file
from app.parsers.mapping import FieldMapping, apply_mapping
from app.parsers.mapping import suggest_mapping as _suggest_mapping

logger = logging.getLogger(__name__)

# AU (abbreviated authors) is left out on purpose: mapping it too would add every
# author twice next to FAU.
_SUGGESTION_ALIASES: dict[str, list[str]] = {
    "title": ["ti"],
    "authors": ["fau"],
    "abstract": ["ab"],
    "journal": ["jt", "ta"],
    "volume": ["vi"],
    "issue": ["ip"],
    "pages": ["pg"],
    "doi": ["doi"],
    "pmid": ["pmid"],
    "language": ["la"],
    "publication_type": ["pt"],
    "publisher": ["pb"],
    "keywords": ["ot", "mh"],
    "date": ["dp"],
    "issn": ["is"],
    "other_ids": ["pmc", "mid"],
}

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9]{1,3}) *-(?: (?P<value>.*))?$")
_ID_TAGS = ("AID", "LID")
_DOI_SUFFIX = " [doi]"
_DOI_TAG = "DOI"
_REQUIRED_TAG = "PMID"


def _doi_from_id(value: str) -> str | None:
    stripped = value.strip()
    if not stripped.endswith(_DOI_SUFFIX):
        return None
    return stripped.removesuffix(_DOI_SUFFIX).strip() or None


def parse_nbib_text(text: str, mapping: FieldMapping) -> ParseResult:
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    def skip(line_number: int, reason: str) -> None:
        skipped.append(SkippedRow(line_number, reason))
        logger.warning("Skipping NBIB record at line %d: %s", line_number, reason)

    values: dict[str, list[str]] = {}
    start_line = 0
    last_tag: str | None = None

    def finish_record() -> None:
        if not values:
            return
        if _REQUIRED_TAG not in values:
            skip(start_line, f"record has no {_REQUIRED_TAG} tag")
            return
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
        record = apply_mapping(raw_fields, mapping)
        rows.append(ParsedRow(record=record, raw_fields=raw_fields))

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            finish_record()
            values, last_tag = {}, None
            continue

        match = _TAG_LINE.match(line)
        if match is None:
            if last_tag is None:
                skip(line_number, "text outside a record")
            else:
                values[last_tag][-1] += " " + line.strip()
            continue

        tag = match["tag"]
        if last_tag is None:
            start_line = line_number
        values.setdefault(tag, []).append((match["value"] or "").strip())
        last_tag = tag

    finish_record()
    return ParseResult(rows=rows, skipped=skipped)


def parse_nbib_file(path: Path, mapping: FieldMapping) -> ParseResult:
    return parse_nbib_text(decode_file(path), mapping)


def read_nbib_tags(path: Path) -> list[str]:
    tags: dict[str, None] = {}
    for line in decode_file(path).splitlines():
        match = _TAG_LINE.match(line)
        if match is None:
            continue
        tags.setdefault(match["tag"])
        if match["tag"] in _ID_TAGS and _doi_from_id(match["value"] or "") is not None:
            tags.setdefault(_DOI_TAG)
    return list(tags)


def suggest_nbib_mapping(tags: list[str]) -> FieldMapping:
    mapping = _suggest_mapping(tags, _SUGGESTION_ALIASES, lenient=False)
    return replace(mapping, list_delimiter="\n")
