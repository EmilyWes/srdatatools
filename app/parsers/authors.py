from typing import Literal

from app.models.record import Author

AmbiguousNameSplit = Literal["none", "first", "last"]


def author_from_name(
    name: str, separator: str, ambiguous: AmbiguousNameSplit = "none"
) -> Author:
    """Splits "Family<separator>Given"; a name without the separator is kept whole.

    ambiguous decides a name with the separator more than once: kept whole, or
    split at the first or last one.
    """
    count = name.count(separator)
    if count == 0 or (count > 1 and ambiguous == "none"):
        return Author(full_name=name)
    if count > 1 and ambiguous == "last":
        family, _, given = name.rpartition(separator)
    else:
        family, _, given = name.partition(separator)
    return Author(full_name=name, family_name=family.strip(), given_name=given.strip())
