import logging
import re
from pathlib import Path

from app.parsers.common import ParsedRow, ParseResult, SkippedRow, decode_file
from app.parsers.mapping import FieldMapping, apply_mapping

logger = logging.getLogger(__name__)

_TAG_LINE = re.compile(r"^(?P<tag>[A-Z][A-Z0-9])  -(?: (?P<value>.*))?$")
_END_TAG = "ER"
_TYPE_TAG = "TY"


def parse_ris_text(text: str, mapping: FieldMapping) -> ParseResult:
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    def skip(line_number: int, reason: str) -> None:
        skipped.append(SkippedRow(line_number, reason))
        logger.warning("Skipping RIS record at line %d: %s", line_number, reason)

    values: dict[str, list[str]] = {}
    start_line = 0
    last_tag: str | None = None

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _TAG_LINE.match(line)
        if match is None:
            if not line.strip():
                continue
            if last_tag is None:
                skip(line_number, "text outside a record")
            else:
                values[last_tag][-1] += "\n" + line.strip()
            continue

        tag = match["tag"]
        if tag == _END_TAG:
            if values and _TYPE_TAG not in values:
                skip(start_line, "record has no TY tag")
            elif values:
                raw_fields = {
                    t: "\n".join(v for v in vs if v) for t, vs in values.items()
                }
                record = apply_mapping(raw_fields, mapping)
                rows.append(ParsedRow(record=record, raw_fields=raw_fields))
            values, last_tag = {}, None
            continue

        if last_tag is None:
            start_line = line_number
        values.setdefault(tag, []).append((match["value"] or "").strip())
        last_tag = tag

    if values:
        skip(start_line, "record is missing its ER terminator")

    return ParseResult(rows=rows, skipped=skipped)


def parse_ris_file(path: Path, mapping: FieldMapping) -> ParseResult:
    return parse_ris_text(decode_file(path), mapping)
