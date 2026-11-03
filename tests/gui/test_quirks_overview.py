from nicegui import ui

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


def test_render_quirks_overview__shows_origin_blocks_in_order() -> None:
    texts = _texts()

    general = texts.index("General")
    assert general < texts.index("CSV / TSV / Excel") < texts.index("Profiles")


def test_render_quirks_overview__skips_an_empty_block() -> None:
    panes = shell()
    entries = [e for e in quirk_entries("csv", "unknown") if e.origin == "general"]

    render_quirks_overview(panes.middle, entries, "CSV / TSV / Excel")

    texts = [e.text for e in panes.middle.descendants() if isinstance(e, ui.label)]
    assert "Profiles" not in texts


def test_render_quirks_overview__shows_used_by() -> None:
    texts = _texts()

    assert any(text.endswith("Used by: Scopus.") for text in texts)


def test_render_quirks_overview__switch_turns_a_quirk_off() -> None:
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


def test_render_quirks_overview__changed_option_is_tinted_blue() -> None:
    screen = _render()
    widget = screen._widgets_for("FirstValue.issn").inputs["delimiter"]
    assert "green-2" in widget.props["bg-color"]

    screen.set_option("FirstValue.issn", "delimiter", ";")

    assert widget.props["bg-color"] == "blue-2"


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

    drop = screen._widgets_for("DropEtAl").switch
    issn = screen._widgets_for("FirstValue.issn").inputs["delimiter"]
    assert drop is not None and drop.value is False
    assert "disable" in drop.props
    assert issn.value == ";"
    assert "readonly" in issn.props
    assert screen.current_choices()["FirstValue.issn"].values == {"delimiter": ";"}
