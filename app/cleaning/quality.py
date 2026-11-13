from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.cleaning.steps import PUBLICATION_TYPES
from app.models.record import CLEANED_DATE
from app.parsers.authors import (
    AUTHOR_JOINER,
    parse_author_ids,
    parse_unsplit_author_ids,
)

# The record fields the checks read.
QUALITY_FIELDS = (
    "publication_date",
    "author_names",
    "author_ids",
    "publication_type",
)
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


def _unmapped_publication_type(fields: Fields) -> bool:
    value: str | None = fields.get("publication_type")
    return bool(value) and value not in PUBLICATION_TYPES


@dataclass(frozen=True)
class Check:
    test: Callable[[Fields], bool]
    # The record table columns that show the problem.
    columns: tuple[str, ...]
    # The full name, when the check's name is shortened to fit.
    hover: str = ""


CHECKS: dict[str, Check] = {
    "Unparsed dates": Check(_unparsed_date, ("publication_date",)),
    "Misaligned authors": Check(_misaligned_authors, ("author_names", "author_ids")),
    "Unmapped pub. types": Check(
        _unmapped_publication_type,
        ("publication_type",),
        hover="Unmapped publication types",
    ),
}


def quality_issues(fields: Fields) -> list[str]:
    return [name for name, check in CHECKS.items() if check.test(fields)]


def problem_columns(counts: Mapping[str, int]) -> list[str]:
    """The data quality column plus the columns of each check that found
    problems."""
    columns = [
        column
        for name, check in CHECKS.items()
        if counts.get(name)
        for column in check.columns
    ]
    return ["data_quality", *columns]
