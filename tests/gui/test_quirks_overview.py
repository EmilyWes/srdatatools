from nicegui import ui
from nicegui.element import Element

from app.gui.layout import shell
from app.gui.quirks_overview import (
    QuirksScreen,
    render_quirks_overview,
    render_view_toggle,
)
from app.parsers.common import FileType
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.overview import (
    ParsingChoices,
    default_choices,
    quirk_boxes,
)
from tests.mappings import mapping_of


def _render(
    file_type: FileType = "csv",
    sources: tuple[str, ...] = (),
    chosen: ParsingChoices | None = None,
    mapping: FieldMapping | None = None,
    middle: Element | None = None,
) -> QuirksScreen:
    return render_quirks_overview(
        middle or shell().middle,
        quirk_boxes(file_type, file_type.upper()),
        default_choices(file_type, sources),
        chosen,
        (lambda: mapping) if mapping is not None else None,
    )


def _labels(middle: Element) -> list[str]:
    return [e.text for e in middle.descendants() if isinstance(e, ui.label)]


def _tooltip(element: Element) -> str:
    [tooltip] = [e for e in element.descendants() if isinstance(e, ui.tooltip)]
    text: str = tooltip.text
    return text


def _label(middle: Element, text: str) -> ui.label:
    return next(
        e for e in middle.descendants() if isinstance(e, ui.label) and e.text == text
    )


def _buttons(middle: Element, icon: str) -> list[ui.button]:
    return [
        e
        for e in middle.descendants()
        if isinstance(e, ui.button) and e.props.get("icon") == icon
    ]


def test_render_quirks_overview__defaults_give_the_profile_defaults() -> None:
    screen = _render(sources=("scopus",))

    assert screen.current_choices() == default_choices("csv", ("scopus",))


def test_render_quirks_overview__boxes_in_order_with_title_in_the_border() -> None:
    middle = shell().middle

    _render("ris", middle=middle)

    boxes = [e for e in middle.descendants() if e.tag == "fieldset"]
    legends = [box.default_slot.children[0] for box in boxes]
    assert all(legend.tag == "legend" for legend in legends)
    assert [_labels(legend) for legend in legends] == [
        ["Labeling"],
        ["Ordering"],
        ["RIS"],
    ]
    assert all("border" in box.classes for box in boxes)


def test_render_quirks_overview__boxes_are_marked_for_equal_widths() -> None:
    middle = shell().middle

    _render(middle=middle)

    boxes = [e for e in middle.descendants() if e.tag == "fieldset"]
    rows = {box.parent_slot.parent for box in boxes if box.parent_slot}
    assert all("quirk-box" in box.classes for box in boxes)
    assert [("quirk-boxes" in row.classes) for row in rows] == [True]


def test_render_quirks_overview__label_hover_shows_the_explanation() -> None:
    middle = shell().middle

    _render(middle=middle)

    assert _tooltip(_label(middle, "Field-size limit")).startswith("Longest cell")


def test_render_quirks_overview__note_is_grey_text_without_control() -> None:
    middle = shell().middle

    screen = _render("ris", middle=middle)

    note = _label(middle, "Author handling")
    assert "text-grey-6" in note.classes
    assert _tooltip(note).startswith("Author name and affiliation lines")
    assert "ris.author_details" not in screen.widgets


def test_render_quirks_overview__field_size_only_for_csv_and_tsv() -> None:
    assert "field_size_limit" in _render("tsv").widgets
    assert "field_size_limit" not in _render("excel").widgets


def test_render_quirks_overview__text_box_is_prefilled_and_tinted_when_changed() -> (
    None
):
    screen = _render("ris", sources=("asreview",))
    widget = screen.widgets["label_include"]
    assert widget.value == "asreview_relevant"
    assert "bg-color" not in widget.props

    screen.set_value("label_include", "")

    assert widget.props["bg-color"] == "blue-2"
    assert screen.current_choices().label_include == ""


def test_render_quirks_overview__labeling_box_has_a_text_box_per_decision() -> None:
    middle = shell().middle
    screen = _render(middle=middle)

    assert {"Include", "Exclude", "Maybe", "Unlabeled"} <= set(_labels(middle))
    assert isinstance(screen.widgets["label_include"], ui.input)
    assert screen.widgets["label_unlabeled"].value == ""

    screen.set_value("label_include", "asreview_relevant")

    assert screen.current_choices().label_include == "asreview_relevant"


def test_render_quirks_overview__field_size_limit_is_numeric() -> None:
    screen = _render()

    screen.set_value("field_size_limit", 500)

    assert screen.current_choices().field_size_limit == 500


def test_render_quirks_overview__ordering_offers_keys_sharing_a_target() -> None:
    mapping = mapping_of({"TI": "title", "TT": "title", "PG": "pages"})

    screen = _render(mapping=mapping)

    [select] = screen.order_rows
    assert select.options == ["TI", "TT"]


def test_render_quirks_overview__ordering_picks_in_listed_order() -> None:
    mapping = mapping_of({"TI": "title", "TT": "title", "AB": "title"})
    screen = _render(mapping=mapping)

    screen.order_rows[0].value = "TT"
    screen.order_rows[1].value = "AB"

    assert screen.current_choices().use_first == ["TT", "AB"]
    assert screen.order_rows[2].options == ["TI"]


def test_render_quirks_overview__stale_ordering_pick_is_kept() -> None:
    screen = _render(mapping=mapping_of({"TI": "title", "TT": "title"}))
    screen.order_rows[0].value = "TT"
    screen.current_mapping = lambda: mapping_of({"TI": "title", "TT": "journal"})

    screen.refresh_ordering()

    assert screen.order_rows[0].value == "TT"
    assert screen.current_choices().use_first == ["TT"]


def test_render_quirks_overview__restore_defaults_resets_every_choice() -> None:
    screen = _render(
        sources=("scopus",), mapping=mapping_of({"A": "title", "B": "title"})
    )
    screen.set_value("label_maybe", "?!")
    screen.set_value("field_size_limit", 500)
    screen.order_rows[0].value = "B"

    screen.restore_defaults()

    assert screen.current_choices() == default_choices("csv", ("scopus",))
    assert "bg-color" not in screen.widgets["label_maybe"].props
    assert len(screen.order_rows) == 1


def test_render_quirks_overview__restore_defaults_button_only_when_editable() -> None:
    editable = shell().middle
    _render(middle=editable)
    readonly = shell().middle
    _render(chosen=default_choices("csv", ()), middle=readonly)

    def texts(middle: Element) -> list[str]:
        return [e.text for e in middle.descendants() if isinstance(e, ui.button)]

    assert "Restore defaults" in texts(editable)
    assert texts(readonly) == []


def test_render_quirks_overview__chosen_is_read_only_and_shows_stored_values() -> None:
    chosen = default_choices("csv", ()).model_copy(
        update={"label_maybe": "?!", "use_first": ["TT"]}
    )

    screen = _render(chosen=chosen)

    maybe = screen.widgets["label_maybe"]
    assert maybe.value == "?!" and "readonly" in maybe.props
    assert [select.value for select in screen.order_rows] == ["TT"]
    assert screen.current_choices() == chosen


def test_render_quirks_overview__label_boxes_are_wide() -> None:
    screen = _render()

    assert "w-[7rem]" in screen.widgets["label_include"].classes
    assert "w-[5.5rem]" in screen.widgets["field_size_limit"].classes


def test_render_view_toggle__shows_one_view_and_reports_switches() -> None:
    shell()
    switched: list[str | None] = []

    views = render_view_toggle("mapping", on_change=switched.append)

    assert _shown(views.mapping) and not _shown(views.parsing)
    views.toggle.value = "parsing"
    assert _shown(views.parsing) and not _shown(views.mapping)
    assert switched == ["parsing"]


def test_render_view_toggle__starts_retracted_by_default() -> None:
    shell()

    views = render_view_toggle()

    assert views.toggle.value is None
    assert not _shown(views.mapping) and not _shown(views.parsing)


def test_render_view_toggle__clearing_the_value_retracts_both() -> None:
    shell()
    switched: list[str | None] = []
    views = render_view_toggle("mapping", on_change=switched.append)

    views.toggle.value = None

    assert views.toggle.props["clearable"] is True
    assert not _shown(views.mapping) and not _shown(views.parsing)
    assert switched == [None]


def test_render_view_toggle__starts_on_the_given_view() -> None:
    shell()

    views = render_view_toggle("parsing")

    assert views.toggle.value == "parsing"
    assert _shown(views.parsing) and not _shown(views.mapping)


def test_render_view_toggle__only_mapping_sets_the_width() -> None:
    shell()

    views = render_view_toggle("parsing")

    assert views.mapping.parent_slot is views.parsing.parent_slot
    assert {"w-0", "min-w-full"} <= set(views.parsing.classes)
    # Collapsed, not removed, so the hidden mapping still sets the width.
    assert {"h-0", "invisible"} <= set(views.mapping.classes)
    assert views.mapping.visible


def _shown(element: Element) -> bool:
    return "invisible" not in element.classes
