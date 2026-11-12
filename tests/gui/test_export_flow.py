import asyncio
from pathlib import Path
from typing import Any

import pytest
from nicegui import ui
from nicegui.element import Element
from nicegui.elements.tooltip import Tooltip

from app.export.columns import ExportColumn, ExportRecord, ExportSource
from app.export.options import ExportOptions
from app.gui import export_flow
from app.gui.export_flow import ExportView, pick_save_path, render_export_view
from app.gui.layout import shell
from app.models.record import Record
from tests.gui.clicks import click_and_wait, run_in


class _FakeWindow:
    def __init__(self, result: tuple[str, ...] | None) -> None:
        self._result = result
        self.kwargs: dict[str, Any] = {}

    async def create_file_dialog(
        self, *args: Any, **kwargs: Any
    ) -> tuple[str, ...] | None:
        self.kwargs = kwargs
        return self._result


def _records() -> list[ExportRecord]:
    return [
        ExportRecord(
            id=1,
            record=Record(
                title="Deep learning",
                author_names="LeCun, Yann",
                doi="10.1038/nature14539",
            ),
            sources=[
                ExportSource(
                    vendor="scopus",
                    filename="scopus.csv",
                    raw_fields={"Title": "Deep learning", "Link": "https://x"},
                    ignored_keys=frozenset({"Link"}),
                )
            ],
        ),
        ExportRecord(id=2, record=Record(title="Untitled draft")),
    ]


def _view(
    selected: bool = False,
    options: ExportOptions | None = None,
    **callbacks: Any,
) -> ExportView:
    panes = shell()
    return render_export_view(
        panes.middle,
        _records(),
        options or ExportOptions(),
        selected=selected,
        on_export=callbacks.pop("on_export", lambda p, c, r, o: None),
        **callbacks,
    )


def _row(view: ExportView, key: str) -> Any:
    return next(row for row in view.rows if row.column.key == key)


def _texts(view: ExportView) -> list[str]:
    return [
        element.text
        for element in view.middle.descendants()
        if isinstance(element, ui.label)
    ]


def _tooltip(element: Element) -> str | None:
    tooltips = [c for c in element.default_slot.children if isinstance(c, Tooltip)]
    return tooltips[0].text if tooltips else None


def test_pick_save_path__returns_chosen_path_with_csv_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    window = _FakeWindow((str(tmp_path / "out.csv"),))
    monkeypatch.setattr(export_flow.app.native, "main_window", window)

    assert asyncio.run(pick_save_path()) == tmp_path / "out.csv"
    assert window.kwargs["save_filename"] == "library.csv"


def test_pick_save_path__none_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_flow.app.native, "main_window", _FakeWindow(None))

    assert asyncio.run(pick_save_path()) is None


@pytest.mark.parametrize(
    ("selected", "line"),
    [(False, "2"), (True, "2 (selected)")],
)
def test_render_export_view__says_which_records(selected: bool, line: str) -> None:
    assert line in _texts(_view(selected=selected))


def test_render_export_view__starts_retracted() -> None:
    view = _view()

    [toggle] = [e for e in view.middle.descendants() if isinstance(e, ui.toggle)]
    assert toggle.value is None


def test_render_export_view__one_row_per_column_with_default_names() -> None:
    view = _view()

    assert [row.name.value for row in view.rows] == [c.name for c in view.columns]
    assert _row(view, "title").name.value == "Title"


def test_render_export_view__fill_bar_and_example() -> None:
    view = _view()
    doi = _row(view, "doi")

    assert doi.count.value == 0.5
    assert _tooltip(doi.count) == "1 of 2"
    assert doi.example.text == "10.1038/nature14539"


def test_export_view__emptied_name_turns_red_and_leaves_column_out() -> None:
    view = _view()
    row = _row(view, "title")

    row.name.value = ""

    assert row.column.name == ""
    assert row.name.props["bg-color"] == "red-2"


def test_export_view__edited_name_turns_blue() -> None:
    view = _view()
    row = _row(view, "title")

    row.name.value = "TI"

    assert row.column.name == "TI"
    assert row.name.props["bg-color"] == "blue-2"


def test_export_view__author_names_row_shows_stored_value() -> None:
    row = _row(_view(), "author_names")

    assert row.example.text == "LeCun, Yann"


def test_export_view__original_data_adds_raw_rows_and_disables_ignored() -> None:
    changes: list[ExportOptions] = []
    view = _view(on_options_change=changes.append)
    _row(view, "title").name.value = "TI"

    view.option_widgets["original_data"].value = True

    keys = [row.column.key for row in view.rows]
    assert keys[-2:] == ["raw:Title", "raw:Link"]
    assert _row(view, "raw:Title").name.value == "Title (original)"
    assert _row(view, "title").name.value == "TI"
    assert view.option_widgets["ignored_columns"].enabled is False
    assert changes[-1].original_data is True


def test_export_view__empty_columns_option_adds_empty_rows() -> None:
    view = _view()
    assert "abstract" not in [row.column.key for row in view.rows]

    view.option_widgets["empty_columns"].value = True

    assert "abstract" in [row.column.key for row in view.rows]


def test_export_view__ignored_columns_adds_only_ignored_raw_rows() -> None:
    view = _view()

    view.option_widgets["ignored_columns"].value = True

    raw_keys = [r.column.key for r in view.rows if r.column.key.startswith("raw:")]
    assert raw_keys == ["raw:Link"]


def test_export_view__restore_defaults_resets_options_and_calls_back() -> None:
    restores: list[None] = []
    view = _view(
        options=ExportOptions(delimiter=";", original_data=True),
        on_restore_options=lambda: restores.append(None),
    )

    view._restore_options()

    assert view.options == ExportOptions()
    assert restores == [None]
    assert not any(row.column.key.startswith("raw:") for row in view.rows)


def test_export_view__export_disabled_until_a_path_is_chosen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    view = _view()
    assert view.export_button is not None
    assert view.export_button.enabled is False
    assert _tooltip(view.export_button) == "choose a target file"
    monkeypatch.setattr(
        export_flow.app.native, "main_window", _FakeWindow((str(tmp_path / "a.csv"),))
    )

    run_in(view.middle, view._choose_path())

    assert view.export_button.enabled is True
    assert _tooltip(view.export_button) is None
    assert str(tmp_path / "a.csv") in _texts(view)


def test_export_view__export_disabled_without_records() -> None:
    view = render_export_view(
        shell().middle,
        [],
        ExportOptions(),
        selected=False,
        on_export=lambda p, c, r, o: None,
    )
    view.path = Path("library.csv")
    view._refresh_export_button()

    assert view.export_button is not None
    assert view.export_button.enabled is False
    assert _tooltip(view.export_button) == "no records to export"


def test_export_view__export_passes_path_columns_records_and_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, list[ExportColumn], list[ExportRecord], ExportOptions]] = []
    view = _view(on_export=lambda *args: calls.append(args))
    view.path = tmp_path / "library.csv"
    view._refresh_export_button()
    assert view.export_button is not None

    click_and_wait(view.export_button, monkeypatch)

    [(path, columns, records, options)] = calls
    assert path == tmp_path / "library.csv"
    assert columns is view.columns
    assert [record.id for record in records] == [1, 2]
    assert options == view.options


def test_export_view__maximum_length_box_sets_option_and_empty_restores_default() -> (
    None
):
    view = _view()

    view.option_widgets["max_length"].value = 32767
    assert view.options.max_length == 32767
    assert view.option_widgets["max_length"].props["bg-color"] == "blue-2"

    view.option_widgets["max_length"].value = None
    assert view.options.max_length == 131_072
