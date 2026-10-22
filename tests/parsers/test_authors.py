from app.parsers.authors import author_from_name


def test_author_from_name__splits_family_and_given_on_separator() -> None:
    author = author_from_name("Smith, John A.", ",")

    assert author.full_name == "Smith, John A."
    assert author.family_name == "Smith"
    assert author.given_name == "John A."


def test_author_from_name__splits_on_first_separator_only() -> None:
    author = author_from_name("Smith, Jr., John", ", ")

    assert author.family_name == "Smith"
    assert author.given_name == "Jr., John"


def test_author_from_name__without_separator_keeps_full_name_only() -> None:
    author = author_from_name("Müller RT", ", ")

    assert author.full_name == "Müller RT"
    assert author.family_name is None
    assert author.given_name is None
