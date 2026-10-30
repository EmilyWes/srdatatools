from app.parsers.authors import author_from_name


def test_author_from_name__splits_family_and_given_on_separator() -> None:
    author = author_from_name("Smith, John A.", ",")

    assert author.full_name == "Smith, John A."
    assert author.family_name == "Smith"
    assert author.given_name == "John A."


def test_author_from_name__ambiguous_name_is_not_split_by_default() -> None:
    author = author_from_name("Smith, Jr., John", ", ")

    assert author.full_name == "Smith, Jr., John"
    assert author.family_name is None
    assert author.given_name is None


def test_author_from_name__ambiguous_name_splits_at_first_separator() -> None:
    author = author_from_name("Smith, Jr., John", ", ", "first")

    assert author.family_name == "Smith"
    assert author.given_name == "Jr., John"


def test_author_from_name__ambiguous_name_splits_at_last_separator() -> None:
    author = author_from_name("Smith, Jr., John", ", ", "last")

    assert author.family_name == "Smith, Jr."
    assert author.given_name == "John"


def test_author_from_name__without_separator_keeps_full_name_only() -> None:
    author = author_from_name("Müller RT", ", ")

    assert author.full_name == "Müller RT"
    assert author.family_name is None
    assert author.given_name is None
