from typing import Literal

from app.models.record import Author

AmbiguousNameSplit = Literal["none", "first", "last"]


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
