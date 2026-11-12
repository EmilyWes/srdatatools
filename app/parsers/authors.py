import logging
import re

logger = logging.getLogger(__name__)

AUTHOR_JOINER = "|"
ID_JOINER = ", "
_ORCID_URL = re.compile(r"^https?://orcid\.org/")
_UNSPLIT_IDS = re.compile(r"(?:^|, )(?P<key>[^:\[\]]+):\[(?P<value>[^\]]*)\]")

# One list of "key:value" ids per author, in author order.
AuthorIds = list[list[str]]


def unsplit_author_ids(key: str, value: str) -> str:
    """A column holding every author's ids, stored as "key:[value]" until
    cleaning splits it per author."""
    return f"{key}:[{value}]"


def parse_unsplit_author_ids(value: str | None) -> list[tuple[str, str]]:
    return [(m["key"], m["value"]) for m in _UNSPLIT_IDS.finditer(value or "")]


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
