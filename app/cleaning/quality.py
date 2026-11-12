from collections.abc import Callable, Mapping
from typing import Any

from app.models.record import CLEANED_DATE
from app.parsers.authors import (
    AUTHOR_JOINER,
    parse_author_ids,
    parse_unsplit_author_ids,
)

# The record fields the checks read.
QUALITY_FIELDS = ("publication_date", "author_names", "author_ids")
ISSUE_JOINER = " | "

Fields = Mapping[str, Any]


def _unparsed_date(fields: Fields) -> bool:
    date: str | None = fields.get("publication_date")
    return bool(date) and CLEANED_DATE.fullmatch(date or "") is None


def _misaligned_authors(fields: Fields) -> bool:
    """Unsplit ids aren't per author yet, so they count as misaligned."""
    names, ids = fields.get("author_names"), fields.get("author_ids")
    if not ids:
        return False
    if parse_unsplit_author_ids(ids):
        return True
    name_count = len(names.split(AUTHOR_JOINER)) if names else 0
    return len(parse_author_ids(ids)) > name_count


CHECKS: dict[str, Callable[[Fields], bool]] = {
    "Unparsed dates": _unparsed_date,
    "Misaligned authors": _misaligned_authors,
}


def quality_issues(fields: Fields) -> list[str]:
    return [name for name, check in CHECKS.items() if check(fields)]
