import datetime
from dataclasses import asdict
from typing import Any

import pytest
from nicegui import ui
from nicegui.element import Element

from app.db.models import SourceFile
from app.gui.layout import shell
from app.gui.source_file_view import render_source_file_view
from app.parsers.common import FileSummary
from app.parsers.mapping import FieldMapping
from tests.gui.clicks import click_and_wait


def _source_file(skipped_rows: list[dict[str, Any]]) -> SourceFile:
    return SourceFile(
        filename="pubmed.nbib",
        path="/imports/pubmed.nbib",
        format="nbib",
        source="pubmed",
        imported_at=datetime.datetime(2026, 1, 1, 9, 5),
        row_count=3,
        skipped_rows=skipped_rows,
        field_mapping=asdict(
            FieldMapping(targets={"TI": "title"}, list_delimiter="\n")
        ),
        suggested_mapping=asdict(
            FieldMapping(targets={"TI": "title", "AB": "abstract"}, list_delimiter="\n")
        ),
        file_summary=asdict(
            FileSummary({"TI": "A title", "AB": "An abstract"}, {"TI": 3, "AB": 2}, 3)
        ),
    )


def _labels(middle: Element) -> list[str]:
    return [
        element.text
        for element in middle.descendants()
        if isinstance(element, ui.label)
    ]


def _table(middle: Element) -> ui.table:
    return next(
        element for element in middle.descendants() if isinstance(element, ui.table)
    )


def _button(element: Element, text: str) -> ui.button:
    return next(
        child
        for child in element.descendants()
        if isinstance(child, ui.button) and child.text == text
    )


def _dialog(middle: Element) -> ui.dialog:
    # Dialogs live in the client layout, which every test in this run shares.
    return [
        element
        for element in middle.client.layout.descendants()
        if isinstance(element, ui.dialog)
    ][-1]


def _click(element: ui.button) -> None:
    click_listener = next(iter(element._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)


def _render(
    skipped_rows: list[dict[str, Any]] | None = None,
) -> tuple[Element, list[None]]:
    panes = shell()
    removed: list[None] = []
    render_source_file_view(
        panes.middle,
        _source_file(skipped_rows or []),
        records_in_library=3,
        on_remove=lambda: removed.append(None),
    )
    return panes.middle, removed


def test_render_source_file_view__shows_metadata_and_record_count() -> None:
    middle, _ = _render()

    labels = _labels(middle)
    for text in [
        "pubmed.nbib",
        "PubMed",
        "nbib",
        "2026-01-01 09:05",
        "/imports/pubmed.nbib",
        "3",
    ]:
        assert text in labels


def test_render_source_file_view__lists_skipped_rows() -> None:
    skipped = [{"row_number": 4, "reason": "row is blank"}]

    middle, _ = _render(skipped)

    assert "Skipped on import: 1" in _labels(middle)
    assert _table(middle).rows == skipped


def test_render_source_file_view__zero_skipped_still_shows_count_and_table() -> None:
    middle, _ = _render()

    assert "Skipped on import: 0" in _labels(middle)
    assert _table(middle).rows == []


def test_render_source_file_view__confirming_remove_calls_on_remove() -> None:
    middle, removed = _render()

    _click(_button(middle, "Remove from library"))
    _click(_button(_dialog(middle), "Remove"))

    assert removed == [None]


def test_render_source_file_view__confirming_remove_awaits_async_on_remove(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panes = shell()
    removed: list[None] = []

    async def on_remove() -> None:
        removed.append(None)

    render_source_file_view(
        panes.middle, _source_file([]), records_in_library=3, on_remove=on_remove
    )

    _click(_button(panes.middle, "Remove from library"))
    click_and_wait(_button(_dialog(panes.middle), "Remove"), monkeypatch)

    assert removed == [None]


def test_render_source_file_view__cancel_does_not_remove() -> None:
    middle, removed = _render()

    _click(_button(middle, "Remove from library"))
    _click(_button(_dialog(middle), "Cancel"))

    assert removed == []


def test_render_source_file_view__shows_saved_mapping_readonly() -> None:
    middle, _ = _render()

    selects = {
        element.value: element
        for element in middle.descendants()
        if isinstance(element, ui.select)
    }
    assert set(selects) == {"title", "ignore"}
    assert all("readonly" in select.props for select in selects.values())
    labels = _labels(middle)
    assert "Field mapping" in labels
    assert "An abstract" in labels
