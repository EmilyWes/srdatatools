import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, fields, replace
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel

from app.parsers.authors import AmbiguousNameSplit
from app.parsers.mapping import LINE_DELIMITER
from app.parsers.profiles import PROFILES, FormatProfile, profile_for
from app.parsers.profiles.default import DEFAULT_PROFILES
from app.parsers.quirks import ContinueToNextField, RecordQuirk

Origin = Literal["general", "type"]
Kind = Literal["toggleable", "setting", "parser"]

# Listing only: these Types show each other's quirks, their profiles stay separate.
_COLUMN_TYPES = ("csv", "tsv", "excel")
_FIELD_SIZE_TYPES = frozenset({"csv", "tsv"})

_ISSN_QUALIFIERS = "skip_issn_isbn_qualifiers"
_MINUS_ONE = "minus_one_unlabeled"
_NAME_SPLIT = "ambiguous_name_split"
_FIELD_SIZE = "csv_field_size_limit"
_PLACEHOLDER_SEPARATOR = ";"


class QuirkChoice(BaseModel):
    on: bool
    values: dict[str, str] = {}


QuirkChoices = dict[str, QuirkChoice]


@dataclass(frozen=True)
class QuirkOption:
    name: str
    label: str
    choices: dict[str, str] | None = None
    # Delimiters and separators may be or end in a space.
    strip: bool = True
    numeric: bool = False


@dataclass(frozen=True)
class QuirkEntry:
    key: str
    origin: Origin
    kind: Kind
    title: str
    explanation: str
    default: QuirkChoice
    options: tuple[QuirkOption, ...] = ()
    details: tuple[str, ...] = ()
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Text:
    title: str
    explanation: str
    editable: tuple[str, ...] = ()


_RECORD_QUIRK_TEXTS: dict[str, _Text] = {
    "FirstValue.isbn": _Text(
        "Keep first ISBN",
        "Books often carry several ISBNs (print, electronic), e.g. one ISBN line"
        " each in NBIB; splits on the delimiter and keeps only the first.",
        ("delimiter",),
    ),
    "DropEtAl": _Text(
        'Drop "et al."',
        'Some exports (e.g. PubMed CSV) end a long author list with "et al.";'
        " removes it so it isn't stored as an author.",
    ),
    "FirstValue.issn": _Text(
        "Keep first ISSN",
        "Some exports (e.g. OpenAlex) list several ISSNs in one value;"
        " splits on the delimiter and keeps only the first.",
        ("delimiter",),
    ),
    "StripPrefix.pmid": _Text(
        "Strip PubMed URL from PMIDs",
        "Some exports (e.g. OpenAlex) give the PMID as a PubMed link;"
        " keeps only the number.",
        ("prefix",),
    ),
    "ExpandPageRange": _Text(
        "Expand short page ranges",
        "PubMed drops the digits the end page shares with the start page"
        " (521-2); writes the full range (521-522).",
    ),
    "FirstValue.publication_type": _Text(
        "Keep first publication type",
        "NBIB has one PT line per publication type; keeps the first"
        " (usually Journal Article).",
    ),
    "EmbeddedAuthorIds": _Text(
        "Author IDs in names",
        "Scopus appends each author's ID to the full name"
        " (Teng, Yu (60652739200)); moves it to the author's IDs under the ID key.",
        ("id_key",),
    ),
    "AffiliationLeadingName": _Text(
        "Author name before affiliation",
        "Scopus starts each affiliation with the author's name"
        " (Teng Y., Guangxi University); drops the text up to the first separator."
        " An affiliation without the separator is only a name and is dropped.",
        ("separator",),
    ),
    "StripLastAuthorTrailing": _Text(
        "Trailing characters on last author",
        "PubMed CSV ends the author list with a period (…, Doe A.);"
        " strips these characters from the last author's name.",
        ("chars",),
    ),
    "RisNotes": _Text(
        "Values in RIS notes",
        "Scopus packs labelled values into N1 note lines (EID: 2-s2.0-…);"
        " reads them into their fields, even when N1 is set to ignore."
        " A filled field is kept; an other ID is always set.",
    ),
    "IdFromUrl": _Text(
        "Scopus EID from URL",
        "Scopus BibTeX has no EID field, but its url links the record;"
        " reads the EID from it, even when url is set to ignore.",
        ("id_key", "prefix"),
    ),
}

_PLACEHOLDER_TEXTS: dict[str, _Text] = {
    "ContinueToNextField.title": _Text(
        "Placeholder titles count as empty",
        "PubMed writes [Not Available]. when an article has no English title;"
        " treats it as empty so the next row mapped to Title"
        " (e.g. TT, the original-language title) is used.",
    ),
}

_PARSER_BEHAVIOURS: dict[str, tuple[tuple[str, ...], _Text]] = {
    "author_columns": (
        (*_COLUMN_TYPES, "bibtex"),
        _Text(
            "Author columns are matched by position",
            "Author rows (names, ORCID, IDs, affiliations) are split on their"
            " author separator and matched by position: the first non-empty names"
            " row sets the authors. A row with a different number of entries is"
            " ignored (logged for developers, not shown here).",
        ),
    ),
    "bibtex.key_continuation": (
        ("bibtex",),
        _Text(
            "Citation keys with commas",
            "Scopus builds keys from page numbers (Wong200922,24); the text after"
            " the comma is read as part of the key, not as a field.",
        ),
    ),
    "ris.author_details": (
        ("ris",),
        _Text(
            "Author details attach to the author above",
            "An AD/C1 (affiliation), ORCID or ID line only belongs to the author"
            " directly above it. Any other tag in between ends that author, so"
            " Scopus's affiliation block after all authors isn't pinned on the"
            " last one.",
        ),
    ),
}

_OPTION_LABELS = {
    "delimiter": "Delimiter",
    "prefix": "Prefix",
    "chars": "Characters",
    "id_key": "ID key",
    "separator": "Separator",
    "key": "Input key",
    "tag": "Tag",
    "pattern": "URL pattern",
    "notes": "Notes",
    "values": "Placeholder values",
    "case_sensitive": "Case-sensitive",
}
_UNSTRIPPED = frozenset({"delimiter", "separator", "chars"})

_ISSN_QUALIFIER_CHOICES = {"": "None", "Electronic": "Electronic", "Print": "Print"}
_NAME_SPLIT_CHOICES: dict[str, str] = {
    "none": "Don't split",
    "first": "At the first separator",
    "last": "At the last separator",
}

_T = TypeVar("_T", RecordQuirk, ContinueToNextField)


@dataclass(frozen=True)
class _Found:
    instance: Any
    origin: Origin
    used_by: tuple[str, ...]
    on: bool


def quirk_key(quirk: RecordQuirk | ContinueToNextField) -> str:
    name = type(quirk).__name__
    field: str | None = getattr(quirk, "field", None)
    return f"{name}.{field}" if field else name


def _type_group(file_type: str) -> tuple[str, ...]:
    return _COLUMN_TYPES if file_type in _COLUMN_TYPES else (file_type,)


def _catalogue(
    file_type: str, source: str, items: Callable[[FormatProfile], Iterable[_T]]
) -> dict[str, _Found]:
    """Every quirk the Type's group uses, in declaration order (defaults first).

    The selected profile's instance wins, so its arguments are the defaults shown.
    """
    selected = profile_for(source, file_type)
    assert selected is not None
    on = {quirk_key(item): item for item in items(selected)}
    general = set.intersection(
        *({quirk_key(item) for item in items(p)} for p in DEFAULT_PROFILES.values())
    )
    type_default = {quirk_key(item) for item in items(DEFAULT_PROFILES[file_type])}
    group = _type_group(file_type)
    declared: list[tuple[str | None, FormatProfile]] = [
        (None, DEFAULT_PROFILES[t]) for t in group
    ]
    declared += [
        (profile.label, profile.formats[t])
        for profile in PROFILES.values()
        for t in group
        if t in profile.formats
    ]
    found: dict[str, _Found] = {}
    for label, format_profile in declared:
        for item in items(format_profile):
            key = quirk_key(item)
            # Profile-only quirks are listed under General, with who uses them.
            profile_only = key not in type_default
            origin: Origin = (
                "type" if key in type_default and key not in general else "general"
            )
            previous = found.get(key)
            used_by: tuple[str, ...] = previous.used_by if previous else ()
            if profile_only and label is not None and label not in used_by:
                used_by = (*used_by, label)
            instance = on.get(key, previous.instance if previous else item)
            found[key] = _Found(instance, origin, used_by, key in on)
    return found


def _record_quirks(file_type: str, source: str) -> dict[str, _Found]:
    return _catalogue(file_type, source, lambda profile: profile.quirks)


def _placeholders(file_type: str, source: str) -> dict[str, _Found]:
    return _catalogue(
        file_type, source, lambda profile: profile.settings.continue_to_next
    )


def _detail_value(value: object) -> str:
    if value == LINE_DELIMITER:
        return "new line"
    if isinstance(value, re.Pattern):
        pattern: str = value.pattern
        return pattern
    if isinstance(value, dict):
        return ", ".join(f"{k!r} → {v}" for k, v in value.items())
    return repr(value) if isinstance(value, str) else str(value)


def _details(instance: Any, shown: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        f"{_OPTION_LABELS[f.name]}: {_detail_value(getattr(instance, f.name))}"
        for f in fields(instance)
        if f.name not in shown and f.name != "field"
    )


def _option(name: str) -> QuirkOption:
    return QuirkOption(name, _OPTION_LABELS[name], strip=name not in _UNSTRIPPED)


def _record_quirk_entry(key: str, found: _Found) -> QuirkEntry:
    text = _RECORD_QUIRK_TEXTS[key]
    values = {name: getattr(found.instance, name) for name in text.editable}
    return QuirkEntry(
        key=key,
        origin=found.origin,
        kind="toggleable",
        title=text.title,
        explanation=text.explanation,
        default=QuirkChoice(on=found.on, values=values),
        options=tuple(_option(name) for name in text.editable),
        details=_details(found.instance, text.editable),
        used_by=found.used_by,
    )


def _placeholder_values(placeholder: ContinueToNextField) -> str:
    return f"{_PLACEHOLDER_SEPARATOR} ".join(sorted(placeholder.values))


def _placeholder_entry(key: str, found: _Found) -> QuirkEntry:
    text = _PLACEHOLDER_TEXTS[key]
    return QuirkEntry(
        key=key,
        origin=found.origin,
        kind="toggleable",
        title=text.title,
        explanation=text.explanation,
        default=QuirkChoice(
            on=found.on, values={"values": _placeholder_values(found.instance)}
        ),
        options=(QuirkOption("values", f"{_OPTION_LABELS['values']} (;-separated)"),),
        details=_details(found.instance, ("values",)),
        used_by=found.used_by,
    )


def quirk_entries(file_type: str, source: str) -> list[QuirkEntry]:
    profile = profile_for(source, file_type)
    if profile is None:
        raise ValueError(f"unsupported file type: {file_type!r}")
    settings = profile.settings
    entries = [
        QuirkEntry(
            key=_ISSN_QUALIFIERS,
            origin="general",
            kind="toggleable",
            title="Skip ISSN/ISBN qualifiers",
            explanation="Drops a qualifier after an ISSN or ISBN, such as Scopus's"
            " (ISSN) or PubMed's (Print), so only the number is stored. When a"
            " record lists one per medium, the value with the preferred qualifier"
            " comes first; with None, they keep their order in the file. The first"
            " value is kept.",
            default=QuirkChoice(
                on=settings.skip_issn_isbn_qualifiers,
                values={"preferred": settings.preferred_issn_qualifier or ""},
            ),
            options=(
                QuirkOption(
                    "preferred", "Preferred qualifier", _ISSN_QUALIFIER_CHOICES
                ),
            ),
        ),
        QuirkEntry(
            key=_MINUS_ONE,
            origin="general",
            kind="toggleable",
            title="ASReview -1 is unlabeled",
            explanation="ASReview writes -1 for records nobody has screened yet;"
            " reads it as unlabeled instead of unknown.",
            default=QuirkChoice(on=settings.minus_one_unlabeled),
        ),
        QuirkEntry(
            key=_NAME_SPLIT,
            origin="general",
            kind="setting",
            title="Ambiguous author names",
            explanation="A name containing the name separator more than once"
            " (Smith, John, Jr) can't be split reliably: keep it as one full name,"
            " or split at the first or last separator.",
            default=QuirkChoice(
                on=True, values={"split": settings.ambiguous_name_split}
            ),
            options=(QuirkOption("split", "Split", _NAME_SPLIT_CHOICES),),
        ),
    ]
    entries += [
        _placeholder_entry(key, found)
        for key, found in _placeholders(file_type, source).items()
    ]
    entries += [
        _record_quirk_entry(key, found)
        for key, found in _record_quirks(file_type, source).items()
    ]
    if file_type in _FIELD_SIZE_TYPES:
        entries.append(
            QuirkEntry(
                key=_FIELD_SIZE,
                origin="type",
                kind="setting",
                title="CSV field-size limit",
                explanation="Longest cell the CSV reader accepts, in characters."
                " Scopus References cells can be very long; a longer cell stops"
                " the file from being read.",
                default=QuirkChoice(
                    on=True, values={"limit": str(settings.csv_field_size_limit)}
                ),
                options=(QuirkOption("limit", "Characters", numeric=True),),
            )
        )
    entries += [
        QuirkEntry(
            key=key,
            origin="type",
            kind="parser",
            title=text.title,
            explanation=text.explanation,
            default=QuirkChoice(on=True),
        )
        for key, (behaviour_types, text) in _PARSER_BEHAVIOURS.items()
        if file_type in behaviour_types
    ]
    return entries


def _split_placeholders(values: str) -> frozenset[str]:
    return frozenset(
        value.strip() for value in values.split(_PLACEHOLDER_SEPARATOR) if value.strip()
    )


def profile_with(file_type: str, source: str, choices: QuirkChoices) -> FormatProfile:
    """The selected profile with the choices applied; missing keys keep defaults."""
    profile = profile_for(source, file_type)
    if profile is None:
        raise ValueError(f"unsupported file type: {file_type!r}")
    chosen = {
        entry.key: choices.get(entry.key, entry.default)
        for entry in quirk_entries(file_type, source)
    }
    issn = chosen[_ISSN_QUALIFIERS]
    settings = replace(
        profile.settings,
        skip_issn_isbn_qualifiers=issn.on,
        preferred_issn_qualifier=issn.values["preferred"] or None,
        minus_one_unlabeled=chosen[_MINUS_ONE].on,
        ambiguous_name_split=cast(
            AmbiguousNameSplit, chosen[_NAME_SPLIT].values["split"]
        ),
        continue_to_next=tuple(
            replace(
                found.instance,
                values=_split_placeholders(chosen[key].values["values"]),
            )
            for key, found in _placeholders(file_type, source).items()
            if chosen[key].on
        ),
    )
    if _FIELD_SIZE in chosen:
        limit = int(chosen[_FIELD_SIZE].values["limit"])
        settings = replace(settings, csv_field_size_limit=limit)
    quirks = tuple(
        replace(found.instance, **chosen[key].values)
        for key, found in _record_quirks(file_type, source).items()
        if chosen[key].on
    )
    return replace(profile, settings=settings, quirks=quirks)


def dump_choices(choices: QuirkChoices) -> dict[str, Any]:
    return {key: choice.model_dump() for key, choice in choices.items()}


def load_choices(data: dict[str, Any]) -> QuirkChoices:
    return {key: QuirkChoice.model_validate(value) for key, value in data.items()}
