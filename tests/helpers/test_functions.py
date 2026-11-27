import pytest

from app.gui.cleaning.steps import SEPARATOR_CANDIDATES
from app.helpers.functions import sniff_separator


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["Teng, Yu; Han, Li", "Doe, J"], ";"),
        (["Baron, Matthew|Norman, David"], "|"),
        (["Smith J\nDoe A"], "\n"),
        (["Smith, John and Doe, Jane"], " and "),
        (["Romano M, Novacek MJ"], None),
        ([None, ""], None),
        (["A; B|C", "D|E"], "|"),
        (["A; B|C"], "|"),
    ],
)
def test_sniff_separator__picks_the_candidate_in_most_values(
    values: list[str | None], expected: str | None
) -> None:
    assert sniff_separator(values, SEPARATOR_CANDIDATES) == expected
