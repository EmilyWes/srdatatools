from nicegui import ui
from nicegui.element import Element

from app.gui.layout import shell
from app.gui.quirks_overview import QuirksScreen, render_quirks_overview
from app.parsers.profiles.overview import QuirkChoice, quirk_entries


def _render(
    file_type: str = "csv",
    source: str = "unknown",
    chosen: dict[str, QuirkChoice] | None = None,
) -> QuirksScreen:
    return render_quirks_overview(
        shell().middle, quirk_entries(file_type, source), "CSV / TSV / Excel", chosen
    )


def _texts() -> list[str]:
    panes = shell()
    entries = quirk_entries("csv", "unknown")
    render_quirks_overview(panes.middle, entries, "CSV / TSV / Excel")
    return [e.text for e in panes.middle.descendants() if isinstance(e, ui.label)]


def test_render_quirks_overview__defaults_give_the_entry_defaults() -> None:
    screen = _render(source="scopus")

    choices = screen.current_choices()

    entries = quirk_entries("csv", "scopus")
    assert choices == {entry.key: entry.default for entry in entries}


def test_render_quirks_overview__shows_general_then_type_block() -> None:
    texts = _texts()

    assert texts.index("General") < texts.index("CSV / TSV / Excel")
    assert "Profiles" not in texts


def test_render_quirks_overview__skips_an_empty_block() -> None:
    panes = shell()
    entries = [e for e in quirk_entries("csv", "unknown") if e.origin == "general"]

    render_quirks_overview(panes.middle, entries, "CSV / TSV / Excel")

    texts = [e.text for e in panes.middle.descendants() if isinstance(e, ui.label)]
    assert "CSV / TSV / Excel" not in texts


def _tooltip(screen: QuirksScreen, key: str) -> str:
    checkbox = screen._widgets_for(key).checkbox
    assert checkbox is not None
    [tooltip] = [e for e in checkbox.descendants() if isinstance(e, ui.tooltip)]
    text: str = tooltip.text
    return text


def test_render_quirks_overview__hover_shows_explanation_used_by_and_details() -> None:
    screen = _render("bibtex")

    hover = _tooltip(screen, "IdFromUrl").splitlines()

    assert hover[0].startswith("Scopus BibTeX has no EID field")
    assert hover[1] == "Used by: Scopus."
    assert hover[2] == "Input key: 'url'"


def test_render_quirks_overview__explanation_is_not_shown_inline() -> None:
    texts = _texts()

    assert not any(text.startswith("Scopus appends") for text in texts)


def test_render_quirks_overview__checkbox_carries_the_title() -> None:
    screen = _render()

    checkbox = screen._widgets_for("DropEtAl").checkbox

    assert checkbox is not None and checkbox.text == 'Drop "et al."'


def test_render_quirks_overview__changed_checkbox_is_blue() -> None:
    screen = _render()
    checkbox = screen._widgets_for("DropEtAl").checkbox
    assert checkbox is not None
    assert "color" not in checkbox.props

    screen.set_on("DropEtAl", False)
    assert checkbox.props["color"] == "blue"

    screen.set_on("DropEtAl", True)
    assert "color" not in checkbox.props


def test_render_quirks_overview__settings_have_no_checkbox() -> None:
    screen = _render()

    assert screen._widgets_for("ambiguous_name_split").checkbox is None
    assert screen._widgets_for("csv_field_size_limit").checkbox is None


def test_render_quirks_overview__checkbox_turns_a_quirk_off() -> None:
    screen = _render()

    screen.set_on("DropEtAl", False)

    assert screen.current_choices()["DropEtAl"] == QuirkChoice(on=False)


def test_render_quirks_overview__empty_box_keeps_the_default() -> None:
    screen = _render()

    screen.set_option("FirstValue.issn", "delimiter", "")

    values = screen.current_choices()["FirstValue.issn"].values
    assert values == {"delimiter": "|"}


def test_render_quirks_overview__delimiter_keeps_spaces() -> None:
    screen = _render()

    screen.set_option("FirstValue.issn", "delimiter", " ; ")

    values = screen.current_choices()["FirstValue.issn"].values
    assert values == {"delimiter": " ; "}


def test_render_quirks_overview__new_line_is_shown_and_typed_as_escape() -> None:
    screen = _render()
    widget = screen._widgets_for("FirstValue.isbn").inputs["delimiter"]

    assert widget.props["placeholder"] == "\\n"
    screen.set_option("FirstValue.isbn", "delimiter", "\\n")
    assert screen.current_choices()["FirstValue.isbn"].values == {"delimiter": "\n"}
    screen.set_option("FirstValue.isbn", "delimiter", ",")
    assert screen.current_choices()["FirstValue.isbn"].values == {"delimiter": ","}


def test_render_quirks_overview__changed_text_box_is_not_tinted() -> None:
    screen = _render()
    widget = screen._widgets_for("FirstValue.issn").inputs["delimiter"]

    screen.set_option("FirstValue.issn", "delimiter", ";")

    assert "bg-color" not in widget.props


def test_render_quirks_overview__changed_dropdown_is_tinted_blue() -> None:
    screen = _render()
    widget = screen._widgets_for("ambiguous_name_split").inputs["split"]
    assert "bg-color" not in widget.props

    screen.set_option("ambiguous_name_split", "split", "last")
    assert widget.props["bg-color"] == "blue-2"

    screen.set_option("ambiguous_name_split", "split", "none")
    assert "bg-color" not in widget.props


def test_render_quirks_overview__restore_defaults_resets_every_choice() -> None:
    screen = _render(source="scopus")
    screen.set_on("DropEtAl", False)
    screen.set_option("FirstValue.issn", "delimiter", ";")
    screen.set_option("csv_field_size_limit", "limit", "500")
    screen.set_option("ambiguous_name_split", "split", "last")

    screen.restore_defaults()

    entries = quirk_entries("csv", "scopus")
    assert screen.current_choices() == {e.key: e.default for e in entries}
    checkbox = screen._widgets_for("DropEtAl").checkbox
    assert checkbox is not None and "color" not in checkbox.props
    assert screen._widgets_for("FirstValue.issn").inputs["delimiter"].value == ""


def _buttons(middle: Element) -> list[str]:
    return [e.text for e in middle.descendants() if isinstance(e, ui.button)]


def test_render_quirks_overview__restore_defaults_button_only_when_editable() -> None:
    editable = shell().middle
    render_quirks_overview(editable, quirk_entries("csv", "unknown"), "CSV")
    readonly = shell().middle
    render_quirks_overview(readonly, quirk_entries("csv", "unknown"), "CSV", {})

    assert _buttons(editable) == ["Restore defaults"]
    assert _buttons(readonly) == []


def test_render_quirks_overview__field_size_limit_is_numeric() -> None:
    screen = _render()

    screen.set_option("csv_field_size_limit", "limit", "500")

    assert screen.current_choices()["csv_field_size_limit"].values == {"limit": "500"}


def test_render_quirks_overview__choice_option_uses_the_selected_value() -> None:
    screen = _render()

    screen.set_option("ambiguous_name_split", "split", "last")

    assert screen.current_choices()["ambiguous_name_split"].values == {"split": "last"}


def test_render_quirks_overview__chosen_is_read_only_and_shows_stored_values() -> None:
    chosen = {
        "DropEtAl": QuirkChoice(on=False),
        "FirstValue.issn": QuirkChoice(on=True, values={"delimiter": ";"}),
    }

    screen = _render(chosen=chosen)

    drop = screen._widgets_for("DropEtAl").checkbox
    issn = screen._widgets_for("FirstValue.issn").inputs["delimiter"]
    assert drop is not None and drop.value is False
    assert "disable" in drop.props
    assert issn.value == ";"
    assert "readonly" in issn.props
    assert screen.current_choices()["FirstValue.issn"].values == {"delimiter": ";"}
