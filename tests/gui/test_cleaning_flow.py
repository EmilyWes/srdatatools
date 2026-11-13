import pytest
from nicegui import ui
from nicegui.element import Element

from app.cleaning.options import CleaningOptions
from app.gui.cleaning_flow import CleaningView, render_cleaning_view
from app.gui.layout import shell
from tests.gui.clicks import click_and_wait


def _render(
    options: CleaningOptions | None = None,
    record_count: int = 3,
    selected: bool = False,
    middle: Element | None = None,
    calls: list[CleaningOptions] | None = None,
) -> CleaningView:
    return render_cleaning_view(
        middle or shell().middle,
        record_count,
        options or CleaningOptions(),
        selected=selected,
        on_clean=(calls if calls is not None else []).append,
    )


def _labels(middle: Element) -> list[str]:
    return [e.text for e in middle.descendants() if isinstance(e, ui.label)]


def _buttons(middle: Element, icon: str) -> list[ui.button]:
    return [
        e
        for e in middle.descendants()
        if isinstance(e, ui.button) and e.props.get("icon") == icon
    ]


def test_render_cleaning_view__boxes_in_order() -> None:
    middle = shell().middle

    _render(middle=middle)

    boxes = [e for e in middle.descendants() if e.tag == "fieldset"]
    titles = [_labels(box.default_slot.children[0]) for box in boxes]
    assert titles == [
        ["ISSN/ISBN"],
        ["Authors"],
        ["Keywords"],
        ["Dates"],
        ["Empty values"],
        ["Identifiers"],
        ["Other"],
        ["From raw fields"],
    ]


@pytest.mark.parametrize(
    ("selected", "expected"), [(False, "1.234"), (True, "1.234 (selected)")]
)
def test_render_cleaning_view__shows_the_record_count(
    selected: bool, expected: str
) -> None:
    middle = shell().middle

    _render(record_count=1234, selected=selected, middle=middle)

    assert expected in _labels(middle)


def test_render_cleaning_view__run_passes_the_current_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[CleaningOptions] = []
    view = _render(calls=calls)
    view.screen.set_value("pages_set", False)

    click_and_wait(view.run_button, monkeypatch)

    assert calls == [CleaningOptions(pages_set=False)]


def test_render_cleaning_view__no_records_disables_run() -> None:
    assert not _render(record_count=0).run_button.enabled
    assert _render(record_count=1).run_button.enabled


def test_render_cleaning_view__opens_on_saved_options_tinted_as_changed() -> None:
    view = _render(CleaningOptions(drop_et_al=False, affiliation_start="; "))

    drop = view.screen.widgets["drop_et_al"]
    start = view.screen.widgets["affiliation_start"]
    assert drop.value is False and drop.props["color"] == "blue"
    assert start.value == "; " and start.props["bg-color"] == "blue-2"
    assert view.screen.current_choices() == CleaningOptions(
        drop_et_al=False, affiliation_start="; "
    )


def test_render_cleaning_view__restore_defaults_goes_to_the_built_in_defaults() -> None:
    view = _render(CleaningOptions(drop_et_al=False, empty_values=["n/a"]))

    view.screen.restore_defaults()

    assert view.screen.current_choices() == CleaningOptions()
    assert "color" not in view.screen.widgets["drop_et_al"].props


def test_render_cleaning_view__checkbox_has_no_text_of_its_own() -> None:
    checkbox = _render().screen.widgets["drop_et_al"]

    assert isinstance(checkbox, ui.checkbox) and checkbox.text == ""


def test_render_cleaning_view__date_order_is_a_dropdown_enabled_by_clean_dates() -> (
    None
):
    screen = _render().screen
    order = screen.widgets["date_order"]

    assert isinstance(order, ui.select) and order.value == "eu"
    screen.set_value("date_order", "us")
    assert screen.current_choices().date_order == "us"
    screen.set_value("clean_dates", False)
    assert not order.enabled


def test_render_cleaning_view__split_authors_enables_its_options() -> None:
    screen = _render().screen
    dependants = [
        screen.widgets[key]
        for key in (
            "names_separator",
            "affiliations_separator",
            "id_from_name",
            "author_strip_extras",
            "affiliation_start",
        )
    ]
    assert all(widget.enabled for widget in dependants)

    screen.set_value("split_authors", False)
    assert not any(widget.enabled for widget in dependants)

    screen.set_value("split_authors", True)
    assert all(widget.enabled for widget in dependants)


def test_render_cleaning_view__preferred_qualifier_greyed_out_without_only_one() -> (
    None
):
    screen = _render().screen
    preferred = screen.widgets["preferred_qualifier"]

    screen.set_value("only_one", False)
    assert not preferred.enabled

    screen.set_value("only_one", True)
    assert preferred.enabled


def test_render_cleaning_view__empty_values_show_saved_plus_a_blank_box() -> None:
    screen = _render().screen

    assert [text.value for text in screen.empty_rows] == ["[Not Available].", ""]
    assert "w-[7rem]" in screen.empty_rows[0].classes


def test_render_cleaning_view__typing_in_the_blank_box_adds_the_next() -> None:
    middle = shell().middle
    screen = _render(middle=middle).screen
    blank = screen.empty_rows[1]

    blank.value = "n"
    blank.value = "none"

    assert screen.empty_rows[1] is blank
    assert [text.value for text in screen.empty_rows] == [
        "[Not Available].",
        "none",
        "",
    ]
    assert len(_buttons(middle, "close")) == 2
    assert screen.current_choices().empty_values == ["[Not Available].", "none"]


def test_render_cleaning_view__cleared_box_stays_but_is_ignored() -> None:
    screen = _render().screen

    screen.empty_rows[0].value = " "

    assert len(screen.empty_rows) == 2
    assert screen.current_choices().empty_values == []


def test_render_cleaning_view__red_remove_button_drops_a_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    middle = shell().middle
    screen = _render(middle=middle).screen
    [remove] = _buttons(middle, "close")
    assert remove.props["color"] == "negative"

    click_and_wait(remove, monkeypatch)

    assert screen.current_choices().empty_values == []
    assert len(screen.empty_rows) == 1
