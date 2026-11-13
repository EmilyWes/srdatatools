import pytest

from app.parsers.common import FileType
from app.parsers.profiles import PROFILES, profile_for
from app.parsers.profiles.overview import (
    ParsingChoices,
    QuirkItem,
    QuirkList,
    default_choices,
    dump_choices,
    load_choices,
    profile_with,
    quirk_boxes,
)

_ALL_TYPES = ("ris", "nbib", "csv", "tsv", "excel", "bibtex")


def _keys(file_type: FileType) -> list[str]:
    return [
        item.key
        for box in quirk_boxes(file_type, "Type")
        for item in box.items
        if isinstance(item, QuirkItem)
    ]


def _type_box_keys(file_type: FileType) -> list[str]:
    box = quirk_boxes(file_type, "Type")[-1]
    return [item.key for item in box.items if isinstance(item, QuirkItem)]


def _with(
    file_type: FileType, sources: tuple[str, ...] = (), **changes: object
) -> ParsingChoices:
    return default_choices(file_type, sources).model_copy(update=changes)


@pytest.mark.parametrize(
    "sources", [(), *((key,) for key in PROFILES)], ids=["unknown", *PROFILES]
)
@pytest.mark.parametrize("file_type", _ALL_TYPES)
def test_profile_with__defaults_reproduce_the_profile(
    file_type: FileType, sources: tuple[str, ...]
) -> None:
    profile = profile_for(sources, file_type)

    assert profile_with(file_type, sources) == profile
    assert profile_with(file_type, sources, default_choices(file_type, sources)) == (
        profile
    )


def test_quirk_boxes__titles_in_order_ending_with_the_type_label() -> None:
    titles = [box.title for box in quirk_boxes("ris", "RIS")]

    assert titles == ["Labeling", "Ordering", "RIS"]


@pytest.mark.parametrize("file_type", ["nbib", "excel"])
def test_quirk_boxes__type_without_items_has_no_box(file_type: FileType) -> None:
    titles = [box.title for box in quirk_boxes(file_type, "Type")]

    assert titles == ["Labeling", "Ordering"]


@pytest.mark.parametrize("file_type", _ALL_TYPES)
def test_quirk_boxes__every_control_key_is_a_choice(file_type: FileType) -> None:
    for box in quirk_boxes(file_type, "Type"):
        for item in box.items:
            key = item.key
            if isinstance(item, QuirkItem) and item.control == "note":
                continue
            assert key in ParsingChoices.model_fields


def test_quirk_boxes__ordering_is_a_list() -> None:
    boxes = {box.title: box for box in quirk_boxes("csv", "CSV")}

    [order] = boxes["Ordering"].items

    assert isinstance(order, QuirkList)
    assert [(p.label, p.control) for p in order.parts] == [("Use first", "select")]


def test_quirk_boxes__type_box_per_type() -> None:
    assert _type_box_keys("csv") == ["field_size_limit"]
    assert _type_box_keys("tsv") == ["field_size_limit"]
    assert _type_box_keys("ris") == ["ris.author_details", "ris.outside_text"]
    assert _type_box_keys("bibtex") == ["bibtex.key_continuation"]


def test_quirk_boxes__type_specific_items_only_in_their_type() -> None:
    assert "field_size_limit" not in _keys("excel")
    assert "ris.outside_text" not in _keys("bibtex")


def test_default_choices__unknown_source_defaults() -> None:
    choices = default_choices("csv", ())

    assert choices.use_first == []
    assert choices.field_size_limit == 1_000_000
    assert (choices.label_include, choices.label_unlabeled) == ("", "")


def test_default_choices__unsupported_type_raises() -> None:
    with pytest.raises(ValueError):
        default_choices("unknown", ())  # type: ignore[arg-type]


def test_profile_with__applies_the_settings() -> None:
    choices = _with(
        "csv",
        label_unlabeled="",
        field_size_limit=500,
        use_first=["B", "A"],
    )

    settings = profile_with("csv", (), choices).settings

    assert settings.label_values == ()
    assert settings.csv_field_size_limit == 500
    assert settings.use_first == ("B", "A")


def test_profile_with__label_values_are_split_lowercased_and_trimmed() -> None:
    choices = _with(
        "ris",
        label_include=" ASReview_relevant | Yes please ",
        label_exclude=" | ",
        label_unlabeled="not seen",
    )

    settings = profile_with("ris", (), choices).settings

    assert settings.label_values == (
        ("asreview_relevant", "include"),
        ("yes please", "include"),
        ("not seen", "unlabeled"),
    )


def test_dump_choices__round_trips() -> None:
    choices = _with("csv", ("scopus",), label_maybe="a|b", use_first=["X"])

    assert load_choices(dump_choices(choices), "csv", ("scopus",)) == choices


def test_load_choices__missing_keys_keep_the_profile_defaults() -> None:
    choices = load_choices({"label_maybe": "?!"}, "csv", ("scopus",))

    assert choices == _with("csv", ("scopus",), label_maybe="?!")


def test_load_choices__drops_choices_that_moved_to_cleaning() -> None:
    choices = load_choices(
        {"drop_et_al": False, "label_maybe": "?!"}, "ris", ("scopus",)
    )

    assert choices == _with("ris", ("scopus",), label_maybe="?!")


def test_load_choices__old_style_choices_fall_back_to_defaults() -> None:
    old = {
        "FirstValue.issn": {"on": True, "values": {"delimiter": ";"}},
        "minus_one_unlabeled": {"on": False, "values": {}},
    }

    assert load_choices(old, "ris", ()) == default_choices("ris", ())
