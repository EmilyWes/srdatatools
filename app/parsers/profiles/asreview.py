import re

from app.models.record import LabelValue
from app.parsers.common import FileType
from app.parsers.mapping import Suggest
from app.parsers.profiles.base import FormatProfile, Profile
from app.parsers.profiles.default import (
    default_settings,
)

_LABEL_HEADER = "asreview_label"
_HEADER_SEPARATOR = re.compile(r"[,;\t]")
_RIS_LABEL_LINE = re.compile(r"^N1  - ASReview_", re.MULTILINE)

# ASReview writes the input file back with its own columns added; a RIS input
# comes back with rispy's field names as headers.
_TABULAR_SUGGESTIONS: dict[str, Suggest] = {
    _LABEL_HEADER: Suggest("label"),
    "asreview_note": Suggest("notes"),
    "number": Suggest("issue"),
}
# The unnamed first column is ASReview's record id; asreview_note is the notes.
_TABULAR_IGNORED = frozenset(
    {
        "",
        "asreview_group_id",
        "asreview_time",
        "secondary_title",
        "author_address",
        "notes",
    }
)
# In the Parsing view's include/exclude/maybe/unlabeled order, so it round-trips.
_RIS_LABEL_VALUES: tuple[tuple[str, LabelValue], ...] = (
    ("asreview_relevant", "include"),
    ("asreview_irrelevant", "exclude"),
    ("asreview_not_seen", "unlabeled"),
)


def _matches_tabular(text: str) -> bool:
    header = text.split("\n", 1)[0]
    names = {
        name.strip().strip('"').lower() for name in _HEADER_SEPARATOR.split(header)
    }
    return _LABEL_HEADER in names


def _matches_ris(text: str) -> bool:
    return bool(_RIS_LABEL_LINE.search(text))


def _tabular(file_type: FileType) -> FormatProfile:
    return FormatProfile(
        suggestions=_TABULAR_SUGGESTIONS,
        matches=_matches_tabular,
        settings=default_settings(file_type),
        ignored_keys=_TABULAR_IGNORED,
    )


ASREVIEW = Profile(
    key="asreview",
    label="ASReview",
    formats={
        "csv": _tabular("csv"),
        "tsv": _tabular("tsv"),
        "excel": _tabular("excel"),
        "ris": FormatProfile(
            suggestions={"n1": Suggest("label")},
            matches=_matches_ris,
            settings=default_settings("ris", label_values=_RIS_LABEL_VALUES),
        ),
    },
)
