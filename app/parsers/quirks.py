import logging
import re
import string
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Protocol

from app.models.record import LabelValue, Record
from app.parsers.authors import (
    author_id,
    format_author_ids,
    merge_author_ids,
    parse_author_ids,
)

# mapping.py imports ParseSettings at runtime, so FieldMapping is only for annotations.
if TYPE_CHECKING:
    from app.parsers.mapping import FieldMapping

logger = logging.getLogger(__name__)

_OTHER_IDS_PREFIX = "other_ids."
_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")
_TRAILING_ET_AL = re.compile(r"[\s,;|]*\bet al\.$")
_TRAILING_ID = re.compile(r"\s*\((?P<id>\d+)\)\s*$")
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DIGITS = re.compile(r"\d+")
_TRAILING_NON_NAME = ".,;:…" + string.whitespace
# Only the plain form: ;volume(issue):pages followed by a full stop.
_CITATION_PARTS = re.compile(
    r";(?P<volume>\d+)\((?P<issue>\d+)\):(?P<pages>\d+(?:-\d+)?)\.(?:\s|$)"
)


@dataclass(frozen=True)
class ParseSettings:
    # Lowercased value -> decision; overrides the built-in spellings.
    label_values: tuple[tuple[str, LabelValue], ...] = ()
    # Python's csv limit is process-wide, so the parser sets it before each parse.
    csv_field_size_limit: int = 1_000_000
    use_first: tuple[str, ...] = ()

    # Cached: the lookups run for every field of every record.
    @cached_property
    def label_lookup(self) -> dict[str, LabelValue]:
        return dict(self.label_values)


NO_QUIRKS = ParseSettings()


class RecordQuirk(Protocol):
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record: ...


def expand_page_range(pages: str) -> str:
    """PubMed drops the leading digits the end page shares with the start: 521-2."""
    match = _PAGE_RANGE.match(pages)
    if match is None or int(match["end"]) >= int(match["start"]):
        return pages
    start, end = match["start"], match["end"]
    return f"{start}-{start[: -len(end)]}{end}"


@dataclass(frozen=True)
class ExpandPageRange:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        if not record.pages:
            return record
        return record.model_copy(update={"pages": expand_page_range(record.pages)})


@dataclass(frozen=True)
class FirstValue:
    field: str
    delimiter: str

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        value: str | None = getattr(record, self.field)
        if not value:
            return record
        first = value.split(self.delimiter)[0].strip()
        return record.model_copy(update={self.field: first})


def _keep_match(record: Record, field: str, pattern: re.Pattern[str]) -> Record:
    value: str | None = getattr(record, field)
    match = pattern.search(value or "")
    if match is None:
        return record
    return record.model_copy(update={field: match[0]})


@dataclass(frozen=True)
class StripDoi:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        return _keep_match(record, "doi", _DOI)


@dataclass(frozen=True)
class StripPmid:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        return _keep_match(record, "pmid", _DIGITS)


@dataclass(frozen=True)
class DropEtAl:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        if not record.author_names:
            return record
        names = _TRAILING_ET_AL.sub("", record.author_names)
        return record.model_copy(update={"author_names": names or None})


@dataclass(frozen=True)
class StripLastAuthorTrailing:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        if not record.author_names:
            return record
        names = record.author_names.rstrip(_TRAILING_NON_NAME)
        return record.model_copy(update={"author_names": names or None})


@dataclass(frozen=True)
class IdFromUrl:
    key: str
    pattern: re.Pattern[str]
    id_key: str
    prefix: str = ""

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        match = self.pattern.search(raw_fields.get(self.key, ""))
        if match is None:
            return record
        other_ids = {**record.other_ids, self.id_key: self.prefix + match[1]}
        return record.model_copy(update={"other_ids": other_ids})


@dataclass(frozen=True)
class RisNotes:
    """Labelled values packed into note lines, e.g. "EID: 2-s2.0-105040180364".

    An other_ids target is always set; a scalar target only fills an empty field.
    """

    tag: str
    notes: dict[str, str]

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        lines = raw_fields.get(self.tag, "").splitlines()
        update: dict[str, object] = {}
        other_ids = dict(record.other_ids)
        for prefix, target in self.notes.items():
            value = next(
                (
                    line.removeprefix(prefix).strip() or None
                    for line in lines
                    if line.startswith(prefix)
                ),
                None,
            )
            if target.startswith(_OTHER_IDS_PREFIX):
                if value is not None:
                    other_ids[target.removeprefix(_OTHER_IDS_PREFIX)] = value
            elif getattr(record, target) is None:
                update[target] = value
        if other_ids != record.other_ids:
            update["other_ids"] = other_ids
        return record.model_copy(update=update)


@dataclass(frozen=True)
class CitationParts:
    """PubMed CSV packs volume, issue and pages into one column, e.g.
    "Nature. 2023 Aug;620(7974):589-594. doi: ...". Only fills empty fields.
    """

    key: str

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        match = _CITATION_PARTS.search(raw_fields.get(self.key, ""))
        if match is None:
            return record
        update = {
            field: match[field]
            for field in ("volume", "issue", "pages")
            if not getattr(record, field)
        }
        return record.model_copy(update=update)


@dataclass(frozen=True)
class EmbeddedAuthorIds:
    """Scopus appends the author id to each full name: "Teng, Yu (60652739200)".

    The ids are added to each author's ids; when they can't be matched to the
    authors by position they are dropped, but the names are still cleaned.
    """

    id_key: str

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        separator = mapping.author_separator("names")
        if not record.author_names or separator is None:
            return record
        names = record.author_names.split(separator)
        matches = [_TRAILING_ID.search(name) for name in names]
        if not any(matches):
            return record
        new_ids = [[author_id(self.id_key, m["id"])] if m else [] for m in matches]
        merged = merge_author_ids(
            parse_author_ids(record.author_ids), new_ids, "author names"
        )
        cleaned = separator.join(_TRAILING_ID.sub("", name) for name in names)
        return record.model_copy(
            update={"author_names": cleaned, "author_ids": format_author_ids(merged)}
        )


@dataclass(frozen=True)
class AffiliationLeadingName:
    """Scopus starts each affiliation with the author's name: "Teng Y., Guangxi ...".

    An affiliation without the separator is only the name, so it is dropped.
    """

    separator: str = ", "

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        between = mapping.author_separator("affiliations")
        if not record.author_affiliations or between is None:
            return record
        kept = []
        for affiliation in record.author_affiliations.split(between):
            name, found, rest = affiliation.partition(self.separator)
            if found and rest:
                leading = name[: len(name) - len(name.lstrip())]
                kept.append(leading + rest)
        return record.model_copy(
            update={"author_affiliations": between.join(kept) or None}
        )
