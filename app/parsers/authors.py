from app.models.record import Author


def author_from_name(name: str, separator: str) -> Author:
    """Splits "Family<separator>Given"; a name without the separator is kept whole."""
    family, found, given = name.partition(separator)
    if not found:
        return Author(full_name=name)
    return Author(full_name=name, family_name=family.strip(), given_name=given.strip())
