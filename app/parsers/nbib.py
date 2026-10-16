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

logger = logging.getLogger(__name__)

# AU is not an alias: mapping it next to FAU would add every author twice.
# suggest_nbib_mapping falls back to it only when the file has no FAU.
_SUGGESTION_ALIASES: dict[str, list[str]] = {
    "title": ["ti"],
    "authors": ["fau", "auid", "ad"],
    "abstract": ["ab"],
    "journal": ["jt", "ta", "bti"],
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
_AUID_TAG = "AUID"
_AD_TAG = "AD"
_ORCID_SCHEME = "ORCID"
_ORCID_URL = re.compile(r"^https?://orcid\.org/")
_MH_TAG = "MH"
_MESH_PREFIX = "[MeSH] "
_EDITOR_TAGS = ("FED", "ED")


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


def _add_auid(author: Author, value: str) -> None:
    """AUID values look like "ORCID: 0000-0001-8894-9875"."""
    scheme, _, identifier = value.partition(":")
    scheme, identifier = scheme.strip(), identifier.strip()
    if not identifier:
        return
    if scheme.upper() == _ORCID_SCHEME:
        author.orcid = _ORCID_URL.sub("", identifier)
    else:
        author.other_ids[scheme.lower()] = identifier


def _author_from_name(name: str) -> Author:
    """FAU is "Family, Given"; AU ("Müller RT") and mononyms have no comma."""
    family, separator, given = name.partition(", ")
    if not separator:
        return Author(full_name=name)
    return Author(full_name=name, family_name=family, given_name=given)


def _authors_from_lines(
    lines: list[tuple[str, str]], author_tags: set[str]
) -> list[Author]:
    """AUID and AD lines belong to the author or editor name line before them."""
    authors: list[Author] = []
    current: Author | None = None
    for tag, value in lines:
        if tag not in author_tags:
            if tag in _EDITOR_TAGS:
                current = None
            continue
        if not value:
            continue
        if tag == _AUID_TAG:
            if current is not None:
                _add_auid(current, value)
        elif tag == _AD_TAG:
            if current is not None:
                current.affiliations.append(Affiliation(name=value))
        else:
            current = _author_from_name(value)
            authors.append(current)
    return authors


def parse_nbib_text(text: str, mapping: FieldMapping) -> ParseResult:
    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    def skip(line_number: int, reason: str) -> None:
        skipped.append(SkippedRow(line_number, reason))
        logger.warning("Skipping NBIB record at line %d: %s", line_number, reason)

    values: dict[str, list[str]] = {}
    order: list[tuple[str, int]] = []
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
        if mapping.targets.get(_MH_TAG) == "keywords" and _MH_TAG in values:
            mapping_fields[_MH_TAG] = "\n".join(
                _MESH_PREFIX + value for value in values[_MH_TAG] if value
            )
        record = apply_mapping(mapping_fields, mapping)
        author_tags = {k for k, t in mapping.targets.items() if t == "authors"}
        if author_tags:
            lines = [(tag, values[tag][i]) for tag, i in order]
            authors = _authors_from_lines(lines, author_tags)
            record = record.model_copy(update={"authors": authors})
        rows.append(ParsedRow(record=record, raw_fields=raw_fields))

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            finish_record()
            values, order, last_tag = {}, [], None
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
        order.append((tag, len(values[tag]) - 1))
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


def suggest_nbib_mapping(
    tags: list[str], alias_overrides: dict[str, list[str]] | None = None
) -> FieldMapping:
    aliases = override_aliases(_SUGGESTION_ALIASES, alias_overrides or {})
    mapping = _suggest_mapping(tags, aliases, lenient=False)
    targets = dict(mapping.targets)
    match_kinds = dict(mapping.match_kinds)
    if "FAU" not in tags and "AU" in tags:
        targets["AU"] = "authors"
        match_kinds["AU"] = "exact"
    return replace(
        mapping, targets=targets, list_delimiter="\n", match_kinds=match_kinds
    )
