import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from app.models.record import Affiliation, Author, Record
from app.parsers.authors import AmbiguousNameSplit, author_from_name

# mapping.py imports ParseSettings at runtime, so FieldMapping is only for annotations.
if TYPE_CHECKING:
    from app.parsers.mapping import FieldMapping

logger = logging.getLogger(__name__)

_OTHER_IDS_PREFIX = "other_ids."
_PAGE_RANGE = re.compile(r"^(?P<start>\d+)-(?P<end>\d+)$")
_ET_AL = "et al."
# "Teng, Yu (60652739200)": Scopus appends the author id to each full name.
_NAME_WITH_ID = re.compile(r"^(?P<name>.*?)\s*\((?P<id>\d+)\)$")


@dataclass(frozen=True)
class ContinueToNextField:
    """Listed values count as empty, so the next key mapped to the field is used."""

    field: str
    values: frozenset[str]
    case_sensitive: bool

    def matches(self, value: str) -> bool:
        if self.case_sensitive:
            return value.strip() in self.values
        return value.strip().lower() in {v.lower() for v in self.values}


@dataclass(frozen=True)
class ParseSettings:
    skip_issn_isbn_qualifiers: bool = False
    minus_one_unlabeled: bool = False
    keyword_prefixes: dict[str, str] = field(default_factory=dict)
    ambiguous_name_split: AmbiguousNameSplit = "none"
    # Python's csv limit is process-wide, so the parser sets it before each parse.
    csv_field_size_limit: int = 1_000_000
    continue_to_next: tuple[ContinueToNextField, ...] = ()


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
    if match is None or len(match["end"]) >= len(match["start"]):
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


@dataclass(frozen=True)
class StripPrefix:
    field: str
    prefix: str

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
        return record.model_copy(update={self.field: value.removeprefix(self.prefix)})


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
    chars: str

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
        full_name = last_name.rstrip(self.chars)
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
class ParallelAuthorColumns:
    """Authors zipped by position from parallel, delimited columns.

    Only columns mapped to authors are read. The first non-empty one sets the
    author count; a column with a different count is ignored with a warning.
    The first non-empty name column wins, e.g. Scopus full names over abbreviated.
    """

    delimiter: str
    name_columns: tuple[str, ...]
    name_separator: str | None = None
    embedded_ids: bool = False
    orcid_column: str | None = None
    orcid_prefix: str = ""
    id_column: str | None = None
    id_key: str = ""
    affiliation_column: str | None = None
    # "Teng Y., Guangxi Cartier Technology Ltd., ...": the leading name is dropped.
    affiliation_separator: str = ", "

    def _split(self, value: str | None) -> list[str]:
        """Keeps empty pieces so positions line up across the columns."""
        if not value or not value.strip():
            return []
        return [piece.strip() for piece in value.split(self.delimiter)]

    def _aligned(self, column: str, values: list[str], count: int) -> list[str]:
        if values and len(values) != count:
            logger.warning(
                "%r has %d entries for %d authors; ignoring it",
                column,
                len(values),
                count,
            )
            return [""] * count
        return values or [""] * count

    def _author(self, name: str, settings: ParseSettings) -> Author:
        if not name:
            return Author()
        if self.name_separator is None:
            return Author(full_name=name)
        return author_from_name(
            name, self.name_separator, settings.ambiguous_name_split
        )

    def apply(
        self,
        raw_fields: dict[str, str],
        record: Record,
        mapping: "FieldMapping",
        settings: ParseSettings,
    ) -> Record:
        mapped = mapping.keys_for("authors")
        name_columns = [c for c in self.name_columns if c in mapped]
        other_columns = [
            c
            for c in (self.orcid_column, self.id_column, self.affiliation_column)
            if c is not None and c in mapped
        ]
        if not name_columns and not other_columns:
            return record
        values = {c: self._split(raw_fields.get(c)) for c in other_columns}
        names = next(
            (split for c in name_columns if (split := self._split(raw_fields.get(c)))),
            [],
        )
        count = next((len(v) for v in (names, *values.values()) if v), 0)
        names = names or [""] * count
        aligned = {c: self._aligned(c, v, count) for c, v in values.items()}

        def column(name: str | None) -> list[str]:
            return aligned.get(name, [""] * count) if name is not None else [""] * count

        orcids = column(self.orcid_column)
        ids = column(self.id_column)
        affiliations = column(self.affiliation_column)
        authors = []
        for name, orcid, author_id, affiliation in zip(
            names, orcids, ids, affiliations, strict=True
        ):
            embedded_id = ""
            if self.embedded_ids and (match := _NAME_WITH_ID.match(name)):
                name, embedded_id = match["name"], match["id"]
            author = self._author(name, settings)
            author.orcid = orcid.removeprefix(self.orcid_prefix) or None
            if author_id := embedded_id or author_id:
                author.other_ids = {self.id_key: author_id}
            _, _, affiliation_name = affiliation.partition(self.affiliation_separator)
            if affiliation_name:
                author.affiliations = [Affiliation(name=affiliation_name)]
            if author.full_name or author.orcid or author.other_ids:
                authors.append(author)
        return record.model_copy(update={"authors": authors})
