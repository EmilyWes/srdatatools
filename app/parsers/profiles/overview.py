import logging
from collections.abc import Collection
from dataclasses import dataclass, replace
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.models.record import LabelValue
from app.parsers.common import FileType
from app.parsers.profiles import FormatProfile, profile_for

logger = logging.getLogger(__name__)

Control = Literal["checkbox", "text", "number", "select", "note"]

_FIELD_SIZE_TYPES: frozenset[FileType] = frozenset({"csv", "tsv"})
_LABEL_VALUES_SEPARATOR = "|"
_LABEL_KEYS: dict[str, LabelValue] = {
    "label_include": "include",
    "label_exclude": "exclude",
    "label_maybe": "maybe",
    "label_unlabeled": "unlabeled",
}


class ParsingChoices(BaseModel):
    label_include: str
    label_exclude: str
    label_maybe: str
    label_unlabeled: str
    use_first: list[str]
    field_size_limit: int


@dataclass(frozen=True)
class QuirkItem:
    key: str
    label: str
    hover: str
    control: Control
    enabled_by: str | None = None
    wide: bool = False
    choices: dict[str, str] | None = None


@dataclass(frozen=True)
class QuirkList:
    """Repeating entries; the GUI supplies the select's options."""

    key: Literal["empty_values", "use_first"]
    parts: tuple[QuirkItem, ...]


@dataclass(frozen=True)
class QuirkBox:
    title: str
    items: tuple[QuirkItem | QuirkList, ...]


_LABELING = QuirkBox(
    "Labeling",
    (
        *(
            QuirkItem(
                key,
                decision.capitalize(),
                f"Label values that mean {decision}, besides the built-in"
                " spellings. Separate values with |; not case-sensitive.",
                "text",
                wide=True,
            )
            for key, decision in _LABEL_KEYS.items()
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
_FIELD_SIZE = QuirkItem(
    "field_size_limit",
    "Field-size limit",
    "Longest cell the CSV reader accepts, in characters; a longer cell stops"
    " the file from being read.",
    "number",
)
_RIS_AUTHOR_DETAILS = QuirkItem(
    "ris.author_details",
    "Author handling",
    "Author name and affiliation lines are joined with |. An author ID line only"
    " belongs to the author directly above it (affiliation lines may sit in"
    " between); any other tag in between ends that author.",
    "note",
)
_RIS_OUTSIDE_TEXT = QuirkItem(
    "ris.outside_text",
    "Text outside records",
    "Lines between an ER and the next record's first tag are ignored, such as"
    " ASReview's record numbers (1., 2., …).",
    "note",
)
_KEY_CONTINUATION = QuirkItem(
    "bibtex.key_continuation",
    "Citation keys with commas",
    "Scopus builds keys from page numbers (Wong200922,24); the text after the"
    " comma is read as part of the key, not as a field.",
    "note",
)


def _type_items(file_type: FileType) -> tuple[QuirkItem, ...]:
    items: list[QuirkItem] = []
    if file_type in _FIELD_SIZE_TYPES:
        items.append(_FIELD_SIZE)
    if file_type == "ris":
        items += [_RIS_AUTHOR_DETAILS, _RIS_OUTSIDE_TEXT]
    if file_type == "bibtex":
        items.append(_KEY_CONTINUATION)
    return tuple(items)


def quirk_boxes(file_type: FileType, type_label: str) -> list[QuirkBox]:
    """A Type with nothing of its own gets no box."""
    type_items = _type_items(file_type)
    type_box = [QuirkBox(type_label, type_items)] if type_items else []
    return [_LABELING, _ORDERING, *type_box]


def _profile(file_type: FileType, sources: Collection[str]) -> FormatProfile:
    profile = profile_for(sources, file_type)
    if profile is None:
        raise ValueError(f"unsupported file type: {file_type!r}")
    return profile


def default_choices(file_type: FileType, sources: Collection[str]) -> ParsingChoices:
    profile = _profile(file_type, sources)
    settings = profile.settings
    return ParsingChoices(
        **{
            key: _LABEL_VALUES_SEPARATOR.join(
                value for value, label in settings.label_values if label == decision
            )
            for key, decision in _LABEL_KEYS.items()
        },
        use_first=list(settings.use_first),
        field_size_limit=settings.csv_field_size_limit,
    )


def _label_values(choices: ParsingChoices) -> tuple[tuple[str, LabelValue], ...]:
    pairs: list[tuple[str, LabelValue]] = []
    for key, decision in _LABEL_KEYS.items():
        for value in getattr(choices, key).split(_LABEL_VALUES_SEPARATOR):
            if value.strip():
                pairs.append((value.strip().lower(), decision))
    return tuple(pairs)


def profile_with(
    file_type: FileType,
    sources: Collection[str],
    choices: ParsingChoices | None = None,
) -> FormatProfile:
    """The sources' profile with the choices applied; None keeps its defaults."""
    profile = _profile(file_type, sources)
    if choices is None:
        return profile
    settings = replace(
        profile.settings,
        label_values=_label_values(choices),
        csv_field_size_limit=choices.field_size_limit,
        use_first=tuple(choices.use_first),
    )
    return replace(profile, settings=settings)


def dump_choices(choices: ParsingChoices) -> dict[str, Any]:
    return choices.model_dump(mode="json")


def load_choices(
    data: dict[str, Any], file_type: FileType, sources: Collection[str]
) -> ParsingChoices:
    """Unknown keys are dropped and missing ones keep the profile's defaults."""
    defaults = default_choices(file_type, sources)
    fields = ParsingChoices.model_fields
    known = {key: value for key, value in data.items() if key in fields}
    try:
        return ParsingChoices.model_validate({**defaults.model_dump(), **known})
    except ValidationError:
        logger.warning("Stored parsing choices %r don't fit; using defaults", data)
        return defaults
