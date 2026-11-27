import logging
import re

logger = logging.getLogger(__name__)

# Between one author's different IDs of the same key.
SAME_KEY_JOINER = " | "
_ORCID_URL = re.compile(r"^https?://orcid\.org/")

# ID key -> one value per author, in author order ("" for an author without one).
AuthorIds = dict[str, list[str]]
# Per author, in author order: its (key, value) IDs.
AuthorSlots = list[list[tuple[str, str]]]


def strip_orcid_url(value: str) -> str:
    return _ORCID_URL.sub("", value)


def clean_author_id(value: str) -> str:
    return strip_orcid_url(value.strip())


def add_author_id(existing: str, new: str) -> str:
    """An ID the author already has isn't added again."""
    ids = existing.split(SAME_KEY_JOINER) if existing else []
    if new and new not in ids:
        ids.append(new)
    return SAME_KEY_JOINER.join(ids)


def ids_by_key(slots: AuthorSlots) -> AuthorIds:
    ids: AuthorIds = {}
    for index, slot in enumerate(slots):
        for key, value in slot:
            values = ids.setdefault(key, [""] * len(slots))
            values[index] = add_author_id(values[index], clean_author_id(value))
    return ids


def ids_of_key(ids: AuthorIds, key: str) -> list[str]:
    """One value per author, also when no author has that key: as many as the
    other keys have."""
    if key in ids:
        return ids[key]
    return [""] * max(map(len, ids.values()), default=0)


def merge_author_ids(ids: AuthorIds, key: str, new: list[str]) -> AuthorIds:
    """A different author count can't be matched by position, so the new IDs are
    then ignored."""
    existing = ids.get(key)
    if existing is None:
        return {**ids, key: new}
    if len(existing) != len(new):
        logger.warning(
            "%d authors' %r IDs for %d authors; ignoring them",
            len(new),
            key,
            len(existing),
        )
        return ids
    merged = [
        add_author_id(old, added) for old, added in zip(existing, new, strict=True)
    ]
    return {**ids, key: merged}
