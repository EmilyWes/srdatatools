import logging
import re
from dataclasses import replace
from pathlib import Path

from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
    decode_file,
)
from app.parsers.mapping import FieldMapping, apply_mapping
from app.parsers.mapping import suggest_mapping as _suggest_mapping

logger = logging.getLogger(__name__)

# AU is not an alias: mapping it next to FAU would add every author twice.
# suggest_nbib_mapping falls back to it only when the file has no FAU.
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
    "isbn": ["isbn"],
    "other_ids": ["pmc", "mid"],
}

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9]{1,3}) *-(?: (?P<value>.*))?$")
_ID_TAGS = ("AID", "LID")
_DOI_SUFFIX = " [doi]"
_DOI_TAG = "DOI"
_REQUIRED_TAG = "PMID"
_IS_TAG = "IS"
_ELECTRONIC = "Electronic"
_IS_QUALIFIER = re.compile(r"\s*\((?P<qualifier>[^)]*)\)$")


def _doi_from_id(value: str) -> str | None:
    stripped = value.strip()
    if not stripped.endswith(_DOI_SUFFIX):
        return None
    return stripped.removesuffix(_DOI_SUFFIX).strip() or None


def _issn_from_is(values: list[str]) -> str | None:
    """PubMed writes one IS line per medium, e.g. "1234-5678 (Print)"."""
    issns: list[tuple[str, str | None]] = []
    for value in values:
        match = _IS_QUALIFIER.search(value)
        issn = (value[: match.start()] if match else value).strip()
        if issn:
            issns.append((issn, match["qualifier"] if match else None))
    if not issns:
        return None
    return next((i for i, q in issns if q == _ELECTRONIC), issns[0][0])


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
        mapping_fields = dict(raw_fields)
        if (issn := _issn_from_is(values.get(_IS_TAG, []))) is not None:
            mapping_fields[_IS_TAG] = issn
        record = apply_mapping(mapping_fields, mapping)
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


def suggest_nbib_mapping(tags: list[str]) -> FieldMapping:
    mapping = _suggest_mapping(tags, _SUGGESTION_ALIASES, lenient=False)
    targets = dict(mapping.targets)
    match_kinds = dict(mapping.match_kinds)
    if "FAU" not in tags and "AU" in tags:
        targets["AU"] = "authors"
        match_kinds["AU"] = "exact"
    return replace(
        mapping, targets=targets, list_delimiter="\n", match_kinds=match_kinds
    )
