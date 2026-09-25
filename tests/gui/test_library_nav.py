import datetime

from app.db.models import SourceFile
from app.gui.layout import shell
from app.gui.library_nav import render_left_panel

_SELECTED_CLASS = "bg-blue-100"


def _source_file(id_: int, filename: str) -> SourceFile:
    return SourceFile(
        id=id_,
        filename=filename,
        path=None,
        format="csv",
        imported_at=datetime.datetime(2026, 1, 1),
        row_count=1,
    )


def test_render_left_panel__builds_without_raising() -> None:
    panes = shell()

    render_left_panel(panes.left, panes.middle, [])


def test_render_left_panel__adds_import_and_library_with_no_source_files() -> None:
    panes = shell()

    nav = render_left_panel(panes.left, panes.middle, [])

    assert len(panes.left.default_slot.children) == 3  # Import, separator, Library
    assert list(nav.buttons) == ["library"]


def test_render_left_panel__adds_one_entry_per_source_file() -> None:
    panes = shell()
    source_files = [
        _source_file(1, "pubmed_export.nbib"),
        _source_file(2, "scopus_export.csv"),
    ]

    nav = render_left_panel(panes.left, panes.middle, source_files)

    assert len(panes.left.default_slot.children) == 5
    assert list(nav.buttons) == ["library", "source_file:1", "source_file:2"]


def test_render_left_panel__select_highlights_entry_and_updates_middle() -> None:
    panes = shell()
    source_files = [_source_file(1, "pubmed_export.nbib")]
    nav = render_left_panel(panes.left, panes.middle, source_files)

    nav.select("source_file:1")

    assert nav.selected_key == "source_file:1"
    assert _SELECTED_CLASS in nav.buttons["source_file:1"].classes
    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 1
    assert middle_children[0].text == "pubmed_export.nbib"  # type: ignore[attr-defined]


def test_render_left_panel__switching_selection_removes_previous_highlight() -> None:
    panes = shell()
    source_files = [_source_file(1, "pubmed_export.nbib")]
    nav = render_left_panel(panes.left, panes.middle, source_files)

    nav.select("library")
    nav.select("source_file:1")

    assert _SELECTED_CLASS not in nav.buttons["library"].classes
    assert _SELECTED_CLASS in nav.buttons["source_file:1"].classes


def test_render_left_panel__import_button_shows_placeholder_without_selecting() -> None:
    panes = shell()
    nav = render_left_panel(panes.left, panes.middle, [])

    nav.show_placeholder("Import")

    assert nav.selected_key is None
    middle_children = panes.middle.default_slot.children
    assert middle_children[0].text == "Import"  # type: ignore[attr-defined]


def test_render_left_panel__import_button_uses_on_import_callback_when_given() -> None:
    panes = shell()
    calls: list[None] = []

    nav = render_left_panel(
        panes.left, panes.middle, [], on_import=lambda: calls.append(None)
    )
    import_button = panes.left.default_slot.children[0]
    click_listener = next(iter(import_button._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)

    assert calls == [None]
    assert nav.selected_key is None  # placeholder fallback was not used
