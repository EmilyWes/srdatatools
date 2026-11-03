import logging
from dataclasses import dataclass, replace
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.parsers.authors import AmbiguousNameSplit
from app.parsers.mapping import LINE_DELIMITER
from app.parsers.profiles import FormatProfile, profile_for
from app.parsers.profiles.scopus import EMBEDDED_AUTHOR_IDS, RIS_NOTES, URL_EID
from app.parsers.quirks import (
    AffiliationLeadingName,
    DropEtAl,
    EmptyValues,
    ExpandPageRange,
    FirstValue,
    RecordQuirk,
    StripDoi,
    StripLastAuthorTrailing,
    StripPmid,
)

logger = logging.getLogger(__name__)

Control = Literal["checkbox", "text", "number", "select", "note"]

_FIELD_SIZE_TYPES = frozenset({"csv", "tsv"})
_AUTHOR_COLUMN_TYPES = frozenset({"csv", "tsv", "excel", "bibtex"})
EMPTY_VALUES_SEPARATOR = "|"

_FIRST_PUBLICATION_TYPE = FirstValue("publication_type", LINE_DELIMITER)
_NAME_SPLIT_CHOICES: dict[str, str] = {
    "none": "Don't split",
    "first": "At the first separator",
    "last": "At the last separator",
}


class ParsingChoices(BaseModel):
    strip_extras: bool
    only_one: bool
    preferred_qualifier: str
    drop_et_al: bool
    drop_trailing: bool
    id_from_name: bool
    affiliation_start: str
    name_split: AmbiguousNameSplit
    minus_one_unlabeled: bool
    empty_values: list[tuple[str, str]]
    use_first: list[str]
    strip_doi: bool
    strip_pmid: bool
    pages_set: bool
    field_size_limit: int
    first_publication_type: bool
    ris_notes: bool
    eid_from_url: bool


@dataclass(frozen=True)
class QuirkItem:
    key: str
    label: str
    hover: str
    control: Control
    choices: dict[str, str] | None = None
    enabled_by: str | None = None


@dataclass(frozen=True)
class QuirkList:
    """Repeating entries; the GUI supplies the select's options."""

    key: Literal["empty_values", "use_first"]
    parts: tuple[QuirkItem, ...]


@dataclass(frozen=True)
class QuirkBox:
    title: str
    items: tuple[QuirkItem | QuirkList, ...]


_ISSN_ISBN = QuirkBox(
    "ISSN/ISBN",
    (
        QuirkItem(
            "strip_extras",
            "Strip extras",
            "The input might have qualifiers like (electronic) or (ISSN);"
            " strips everything away and keeps only the pure ISSN/ISBN.",
            "checkbox",
        ),
        QuirkItem(
            "only_one",
            "Only parse one",
            "Some inputs have several ISSN/ISBN values; keeps only one of them:"
            " the first, unless the preferred qualifier picks another.",
            "checkbox",
        ),
        QuirkItem(
            "preferred_qualifier",
            "Preferred qualifier",
            "If a value is followed by a label in brackets, e.g."
            ' "1234-5678 (electronic), 9123-4567 (print)", fill in electronic to'
            " prefer the electronic value. Not case-sensitive.",
            "text",
            enabled_by="only_one",
        ),
    ),
)
_AUTHORS = QuirkBox(
    "Authors",
    (
        QuirkItem(
            "drop_et_al",
            'Drop "et al."',
            'Removes a trailing "et al." while parsing author names.',
            "checkbox",
        ),
        QuirkItem(
            "drop_trailing",
            "Drop trailing",
            "Removes non-name characters, like ... or ., from the end of the last"
            " author's name.",
            "checkbox",
        ),
        QuirkItem(
            "id_from_name",
            "ID from name",
            "Scopus adds the author ID to the name (Doe, John (12345)); reads it as"
            " a separate ID called scopus_author_id.",
            "checkbox",
        ),
        QuirkItem(
            "affiliation_start",
            "Affiliation start",
            "Sometimes an affiliation starts with the author's name; strips"
            " everything up to this delimiter. An affiliation without the"
            " delimiter is only a name and is dropped. Leave empty to keep"
            " affiliations as they are.",
            "text",
        ),
        QuirkItem(
            "name_split",
            "Splitting option",
            "When splitting author names on a separator, that separator might"
            " appear several times (John, Doe, Jr.). Choose not to split, or to"
            " split at the first or last separator.",
            "select",
            choices=_NAME_SPLIT_CHOICES,
        ),
    ),
)
_LABELING = QuirkBox(
    "Labeling",
    (
        QuirkItem(
            "minus_one_unlabeled",
            "ASReview -1 is unlabeled",
            "ASReview writes -1 for records nobody has screened yet;"
            " reads it as unlabeled instead of unknown.",
            "checkbox",
        ),
    ),
)
_EMPTY_VALUES = QuirkBox(
    "Empty values",
    (
        QuirkList(
            "empty_values",
            (
                QuirkItem(
                    "field",
                    "Field",
                    "Select a field for which to enter values that should be"
                    " ignored.",
                    "select",
                ),
                QuirkItem(
                    "values",
                    "Ignore",
                    "These values are replaced with an empty value, so the next"
                    " column mapped to the field can fill it. Separate values"
                    " with |; not case-sensitive.",
                    "text",
                ),
            ),
        ),
    ),
)
_ORDERING = QuirkBox(
    "Ordering",
    (
        QuirkList(
            "use_first",
            (
                QuirkItem(
                    "column",
                    "Use first",
                    "If several input columns map to the same field, use this"
                    " column first instead of the default top-to-bottom order.",
                    "select",
                ),
            ),
        ),
    ),
)
_IDENTIFIERS = QuirkBox(
    "Identifiers",
    (
        QuirkItem(
            "strip_doi",
            "Strip DOI",
            'Strips all extra text from a DOI, leaving e.g. "10.1038/nature12373".',
            "checkbox",
        ),
        QuirkItem(
            "strip_pmid",
            "Strip PMID",
            "Strips all extra text from PMIDs, keeping only the number.",
            "checkbox",
        ),
    ),
)
_OTHER = QuirkBox(
    "Other",
    (
        QuirkItem(
            "pages_set",
            "Pages set",
            "Expands a page range like 512-4 to 512-514. Only acts if the second"
            " value is lower than the first.",
            "checkbox",
        ),
    ),
)

_FIELD_SIZE = QuirkItem(
    "field_size_limit",
    "Field-size limit",
    "Longest cell the CSV reader accepts, in characters; a longer cell stops"
    " the file from being read.",
    "number",
)
_AUTHOR_COLUMNS = QuirkItem(
    "author_columns",
    "Author matching",
    "Author rows (names, ORCID, IDs, affiliations) are split on their author"
    " separator and matched by position: the first non-empty names row sets the"
    " authors. A row with a different number of entries is ignored (logged for"
    " developers, not shown here).",
    "note",
)
_FIRST_PUBLICATION_TYPE_ITEM = QuirkItem(
    "first_publication_type",
    "First pub. type",
    "NBIB can have several rows for publication type; keeps only the first.",
    "checkbox",
)
_RIS_NOTES_ITEM = QuirkItem(
    "ris_notes",
    "Values in RIS notes",
    "Scopus packs labelled values into N1 note lines (EID: 2-s2.0-…); reads them"
    " into their fields, even when N1 is set to ignore. A filled field is kept;"
    " an other ID is always set.",
    "checkbox",
)
_RIS_AUTHOR_DETAILS = QuirkItem(
    "ris.author_details",
    "Author details attach to the author above",
    "An AD/C1 (affiliation), ORCID or ID line only belongs to the author directly"
    " above it. Any other tag in between ends that author, so Scopus's"
    " affiliation block after all authors isn't pinned on the last one.",
    "note",
)
_EID_FROM_URL_ITEM = QuirkItem(
    "eid_from_url",
    "Scopus EID from URL",
    "Scopus BibTeX has no EID field, but its url links the record; reads the EID"
    " from it, even when url is set to ignore.",
    "checkbox",
)
_KEY_CONTINUATION = QuirkItem(
    "bibtex.key_continuation",
    "Citation keys with commas",
    "Scopus builds keys from page numbers (Wong200922,24); the text after the"
    " comma is read as part of the key, not as a field.",
    "note",
)


def _type_items(file_type: str) -> tuple[QuirkItem, ...]:
    items: list[QuirkItem] = []
    if file_type in _FIELD_SIZE_TYPES:
        items.append(_FIELD_SIZE)
    if file_type in _AUTHOR_COLUMN_TYPES:
        items.append(_AUTHOR_COLUMNS)
    if file_type == "nbib":
        items.append(_FIRST_PUBLICATION_TYPE_ITEM)
    if file_type == "ris":
        items += [_RIS_NOTES_ITEM, _RIS_AUTHOR_DETAILS]
    if file_type == "bibtex":
        items += [_EID_FROM_URL_ITEM, _KEY_CONTINUATION]
    return tuple(items)


def quirk_boxes(file_type: str, type_label: str) -> list[QuirkBox]:
    return [
        _ISSN_ISBN,
        _AUTHORS,
        _LABELING,
        _EMPTY_VALUES,
        _ORDERING,
        _IDENTIFIERS,
        _OTHER,
        QuirkBox(type_label, _type_items(file_type)),
    ]


def _profile(file_type: str, source: str) -> FormatProfile:
    profile = profile_for(source, file_type)
    if profile is None:
        raise ValueError(f"unsupported file type: {file_type!r}")
    return profile


def default_choices(file_type: str, source: str) -> ParsingChoices:
    profile = _profile(file_type, source)
    settings, quirks = profile.settings, profile.quirks
    return ParsingChoices(
        strip_extras=settings.issn_isbn_strip_extras,
        only_one=settings.issn_isbn_only_one,
        preferred_qualifier=settings.preferred_issn_qualifier or "",
        drop_et_al=DropEtAl() in quirks,
        drop_trailing=StripLastAuthorTrailing() in quirks,
        id_from_name=EMBEDDED_AUTHOR_IDS in quirks,
        affiliation_start=next(
            (q.separator for q in quirks if isinstance(q, AffiliationLeadingName)), ""
        ),
        name_split=settings.ambiguous_name_split,
        minus_one_unlabeled=settings.minus_one_unlabeled,
        empty_values=[
            (empty.field, EMPTY_VALUES_SEPARATOR.join(sorted(empty.values)))
            for empty in settings.empty_values
        ],
        use_first=list(settings.use_first),
        strip_doi=StripDoi() in quirks,
        strip_pmid=StripPmid() in quirks,
        pages_set=ExpandPageRange() in quirks,
        field_size_limit=settings.csv_field_size_limit,
        first_publication_type=_FIRST_PUBLICATION_TYPE in quirks,
        ris_notes=RIS_NOTES in quirks,
        eid_from_url=URL_EID in quirks,
    )


def _empty_values(field: str, values: str) -> EmptyValues:
    split = (value.strip() for value in values.split(EMPTY_VALUES_SEPARATOR))
    return EmptyValues(field, frozenset(value for value in split if value))


def _quirks(choices: ParsingChoices) -> tuple[RecordQuirk, ...]:
    """ID from name runs before Drop trailing, which would leave its ")" alone."""
    candidates: list[tuple[bool, RecordQuirk]] = [
        (choices.drop_et_al, DropEtAl()),
        (choices.strip_doi, StripDoi()),
        (choices.strip_pmid, StripPmid()),
        (choices.pages_set, ExpandPageRange()),
        (choices.first_publication_type, _FIRST_PUBLICATION_TYPE),
        (choices.id_from_name, EMBEDDED_AUTHOR_IDS),
        (
            bool(choices.affiliation_start),
            AffiliationLeadingName(choices.affiliation_start),
        ),
        (choices.drop_trailing, StripLastAuthorTrailing()),
        (choices.ris_notes, RIS_NOTES),
        (choices.eid_from_url, URL_EID),
    ]
    return tuple(quirk for on, quirk in candidates if on)


def profile_with(
    file_type: str, source: str, choices: ParsingChoices | None = None
) -> FormatProfile:
    """The selected profile with the choices applied; None keeps its defaults."""
    profile = _profile(file_type, source)
    if choices is None:
        return profile
    settings = replace(
        profile.settings,
        issn_isbn_strip_extras=choices.strip_extras,
        issn_isbn_only_one=choices.only_one,
        preferred_issn_qualifier=choices.preferred_qualifier.strip() or None,
        minus_one_unlabeled=choices.minus_one_unlabeled,
        ambiguous_name_split=choices.name_split,
        csv_field_size_limit=choices.field_size_limit,
        empty_values=tuple(
            _empty_values(field, values)
            for field, values in choices.empty_values
            if field and values.strip()
        ),
        use_first=tuple(choices.use_first),
    )
    return replace(profile, settings=settings, quirks=_quirks(choices))


def dump_choices(choices: ParsingChoices) -> dict[str, Any]:
    return choices.model_dump(mode="json")


def load_choices(data: dict[str, Any], file_type: str, source: str) -> ParsingChoices:
    """Unknown keys are dropped and missing ones keep the profile's defaults."""
    defaults = default_choices(file_type, source)
    fields = ParsingChoices.model_fields
    known = {key: value for key, value in data.items() if key in fields}
    try:
        return ParsingChoices.model_validate({**defaults.model_dump(), **known})
    except ValidationError:
        logger.warning("Stored parsing choices %r don't fit; using defaults", data)
        return defaults
