import logging
import re
from typing import Literal

from app.models.record import Author

logger = logging.getLogger(__name__)

AmbiguousNameSplit = Literal["none", "first", "last"]

AUTHOR_JOINER = "|"
ID_JOINER = ", "
_ORCID_URL = re.compile(r"^https?://orcid\.org/")

# One list of "key:value" ids per author, in author order.
AuthorIds = list[list[str]]


def author_from_name(
    name: str,
    separator: str,
    ambiguous: AmbiguousNameSplit = "none",
    family_first: bool = True,
) -> Author:
    """Splits "Family<separator>Given" (or "Given<separator>Family" when not
    family_first); a name without the separator is kept whole.

    ambiguous decides a name with the separator more than once: kept whole, or
    split at the first or last one.
    """
    count = name.count(separator)
    if count == 0 or (count > 1 and ambiguous == "none"):
        return Author(full_name=name)
    if count > 1 and ambiguous == "last":
        before, _, after = name.rpartition(separator)
    else:
        before, _, after = name.partition(separator)
    family, given = (before, after) if family_first else (after, before)
    return Author(full_name=name, family_name=family.strip(), given_name=given.strip())


def strip_orcid_url(value: str) -> str:
    return _ORCID_URL.sub("", value)


def author_id(key: str, value: str) -> str:
    return f"{key}:{strip_orcid_url(value.strip())}"


def format_author_ids(slots: AuthorIds) -> str | None:
    """Empty slots are kept so positions keep matching the authors."""
    if not any(slots):
        return None
    return AUTHOR_JOINER.join(ID_JOINER.join(dict.fromkeys(slot)) for slot in slots)


def parse_author_ids(value: str | None) -> AuthorIds:
    if not value:
        return []
    return [
        [item for item in piece.split(ID_JOINER) if item]
        for piece in value.split(AUTHOR_JOINER)
    ]


def merge_author_ids(existing: AuthorIds, new: AuthorIds, source: str) -> AuthorIds:
    """Adds each author's new ids to their slot; a different author count can't
    be matched by position, so the new ids are then ignored."""
    if not existing:
        return new
    if not new:
        return existing
    if len(new) != len(existing):
        logger.warning(
            "%r has %d authors' ids for %d authors; ignoring it",
            source,
            len(new),
            len(existing),
        )
        return existing
    return [[*old, *added] for old, added in zip(existing, new, strict=True)]
