import asyncio
import datetime

import pytest
from nicegui import background_tasks, core

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
    assert list(nav.buttons) == ["import", "library"]


def test_render_left_panel__adds_one_entry_per_source_file() -> None:
    panes = shell()
    source_files = [
        _source_file(1, "pubmed_export.nbib"),
        _source_file(2, "scopus_export.csv"),
    ]

    nav = render_left_panel(panes.left, panes.middle, source_files)

    # Import, sep, Library, sep, "Imported files" label, source_file:1, source_file:2
    assert len(panes.left.default_slot.children) == 7
    assert list(nav.buttons) == [
        "import",
        "library",
        "source_file:1",
        "source_file:2",
    ]


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


def test_render_left_panel__clicking_import_selects_and_shows_placeholder() -> None:
    panes = shell()
    nav = render_left_panel(panes.left, panes.middle, [])

    import_button = panes.left.default_slot.children[0]
    click_listener = next(iter(import_button._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)

    assert nav.selected_key == "import"
    assert _SELECTED_CLASS in nav.buttons["import"].classes
    middle_children = panes.middle.default_slot.children
    assert middle_children[0].text == "Import"  # type: ignore[attr-defined]


def test_render_left_panel__clicking_import_deselects_previous_selection() -> None:
    panes = shell()
    source_files = [_source_file(1, "pubmed_export.nbib")]
    nav = render_left_panel(panes.left, panes.middle, source_files)
    nav.select("source_file:1")

    import_button = panes.left.default_slot.children[0]
    click_listener = next(iter(import_button._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)

    assert nav.selected_key == "import"
    assert _SELECTED_CLASS not in nav.buttons["source_file:1"].classes
    assert _SELECTED_CLASS in nav.buttons["import"].classes


def test_render_left_panel__import_button_uses_on_import_callback_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panes = shell()
    calls: list[None] = []

    async def on_import() -> None:
        calls.append(None)

    nav = render_left_panel(panes.left, panes.middle, [], on_import=on_import)
    import_button = panes.left.default_slot.children[0]
    click_listener = next(iter(import_button._event_listeners.values()))
    assert click_listener.handler is not None

    async def click_and_wait() -> None:
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        before = set(background_tasks.running_tasks)
        click_listener.handler(None)  # type: ignore[misc]
        scheduled = set(background_tasks.running_tasks) - before
        await asyncio.gather(*scheduled)

    asyncio.run(click_and_wait())

    assert calls == [None]
    assert nav.selected_key == "import"  # import button is highlighted while busy
