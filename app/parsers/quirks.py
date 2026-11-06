import logging
import re
import string
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Protocol

from app.models.record import Affiliation, LabelValue, Record
from app.parsers.authors import AmbiguousNameSplit

# mapping.py imports ParseSettings at runtime, so FieldMapping is only for annotations.
if TYPE_CHECKING:
    from app.parsers.mapping import FieldMapping

logger = logging.getLogger(__name__)

_OTHER_IDS_PREFIX = "other_ids."
_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")
_ET_AL = "et al."
_NAME_WITH_ID = re.compile(r"^(?P<name>.*?)\s*\((?P<id>\d+)\)$")
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DIGITS = re.compile(r"\d+")
_TRAILING_NON_NAME = ".,;:…" + string.whitespace
# Only the plain form: ;volume(issue):pages followed by a full stop.
_CITATION_PARTS = re.compile(
    r";(?P<volume>\d+)\((?P<issue>\d+)\):(?P<pages>\d+(?:-\d+)?)\.(?:\s|$)"
)


@dataclass(frozen=True)
class ParseSettings:
    issn_isbn_strip_extras: bool = False
    issn_isbn_only_one: bool = False
    preferred_issn_qualifier: str | None = None
    # Lowercased value -> decision; overrides the built-in spellings.
    label_values: tuple[tuple[str, LabelValue], ...] = ()
    ambiguous_name_split: AmbiguousNameSplit = "none"
    # Python's csv limit is process-wide, so the parser sets it before each parse.
    csv_field_size_limit: int = 1_000_000
    # Count as empty in any text field, so the next key mapped to it is used.
    empty_values: tuple[str, ...] = ()
    use_first: tuple[str, ...] = ()

    # Cached: the lookups run for every field of every record.
    @cached_property
    def label_lookup(self) -> dict[str, LabelValue]:
        return dict(self.label_values)

    @cached_property
    def empty_lookup(self) -> frozenset[str]:
        return frozenset(value.lower() for value in self.empty_values)


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
        authors = [author for author in record.authors if author.full_name != _ET_AL]
        return record.model_copy(update={"authors": authors})


@dataclass(frozen=True)
class StripLastAuthorTrailing:
    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        last_name = record.authors[-1].full_name if record.authors else None
        if not last_name:
            return record
        authors = list(record.authors)
        full_name = last_name.rstrip(_TRAILING_NON_NAME)
        authors[-1] = authors[-1].model_copy(update={"full_name": full_name})
        return record.model_copy(update={"authors": authors})


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
    """Scopus appends the author id to each full name: "Teng, Yu (60652739200)"."""

    id_key: str

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        authors = []
        for author in record.authors:
            match = _NAME_WITH_ID.match(author.full_name or "")
            if match is None:
                authors.append(author)
                continue
            names = {
                name: _NAME_WITH_ID.sub(r"\g<name>", value)
                for name in ("full_name", "family_name", "given_name")
                if (value := getattr(author, name))
            }
            other_ids = {**author.other_ids, self.id_key: match["id"]}
            authors.append(author.model_copy(update={**names, "other_ids": other_ids}))
        return record.model_copy(update={"authors": authors})


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
        authors = []
        for author in record.authors:
            affiliations = [
                Affiliation(name=name)
                for affiliation in author.affiliations
                if (name := (affiliation.name or "").partition(self.separator)[2])
            ]
            authors.append(author.model_copy(update={"affiliations": affiliations}))
        return record.model_copy(update={"authors": authors})
