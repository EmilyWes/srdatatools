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
                    vendors=("scopus",),
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
        _DEFAULT_PATH,
        selected=selected,
        on_export=callbacks.pop("on_export", lambda p, c, r, o: None),
        **callbacks,
    )


_DEFAULT_PATH = Path("exports") / "library.csv"


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


def test_pick_save_path__opens_in_suggested_folder_with_suggested_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    window = _FakeWindow((str(tmp_path / "out.csv"),))
    monkeypatch.setattr(export_flow.app.native, "main_window", window)

    assert asyncio.run(pick_save_path(tmp_path / "library_1.csv", "csv")) == (
        tmp_path / "out.csv"
    )
    assert window.kwargs["directory"] == str(tmp_path)
    assert window.kwargs["save_filename"] == "library_1.csv"
    assert window.kwargs["file_types"] == ("CSV files (*.csv)",)


def test_pick_save_path__none_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_flow.app.native, "main_window", _FakeWindow(None))

    assert asyncio.run(pick_save_path(_DEFAULT_PATH, "csv")) is None


@pytest.mark.parametrize(
    ("selected", "noun"),
    [(False, "records to:"), (True, "selected records to:")],
)
def test_render_export_view__says_which_records(selected: bool, noun: str) -> None:
    texts = _texts(_view(selected=selected))

    assert texts[texts.index("Exporting") : texts.index("Exporting") + 3] == [
        "Exporting",
        "2",
        noun,
    ]


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


def test_export_view__emptied_name_turns_red() -> None:
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


def test_export_view__default_path_shown_and_export_enabled() -> None:
    view = _view()

    assert view.path_label is not None
    assert view.path_label.text == str(Path("exports") / "library.csv")
    assert _tooltip(view.path_label) == str(_DEFAULT_PATH)
    assert view.export_button is not None
    assert view.export_button.enabled is True
    assert _tooltip(view.export_button) is None


def test_export_view__save_as_starts_from_current_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    view = _view()
    window = _FakeWindow(None)
    monkeypatch.setattr(export_flow.app.native, "main_window", window)

    run_in(view.middle, view._choose_path())

    assert window.kwargs["directory"] == str(_DEFAULT_PATH.parent)
    assert window.kwargs["save_filename"] == "library.csv"
    assert view.path == _DEFAULT_PATH


def _view_at(path: Path) -> ExportView:
    return render_export_view(
        shell().middle,
        _records(),
        ExportOptions(),
        path,
        selected=False,
        on_export=lambda p, c, r, o: None,
    )


def test_export_view__tsv_sets_tab_and_recomputes_default_path(tmp_path: Path) -> None:
    (tmp_path / "library.tsv").touch()
    view = _view_at(tmp_path / "library.csv")
    assert view.file_type_select is not None

    view.file_type_select.value = "tsv"

    assert view.options.file_type == "tsv"
    assert view.options.delimiter == "	"
    assert view.path == tmp_path / "library_1.tsv"


def test_export_view__back_to_csv_sets_comma(tmp_path: Path) -> None:
    view = _view_at(tmp_path / "library.csv")
    assert view.file_type_select is not None
    view.file_type_select.value = "tsv"

    view.file_type_select.value = "csv"

    assert view.options.delimiter == ","
    assert view.path == tmp_path / "library.csv"


def test_export_view__file_type_swaps_extension_of_chosen_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    view = _view_at(tmp_path / "library.csv")
    window = _FakeWindow((str(tmp_path / "mine.csv"),))
    monkeypatch.setattr(export_flow.app.native, "main_window", window)
    run_in(view.middle, view._choose_path())
    assert view.file_type_select is not None

    view.file_type_select.value = "tsv"

    assert view.path == tmp_path / "mine.tsv"
    assert view.path_label is not None
    assert view.path_label.text == str(Path(tmp_path.name) / "mine.tsv")


def test_pick_save_path__excel_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _FakeWindow(None)
    monkeypatch.setattr(export_flow.app.native, "main_window", window)

    asyncio.run(pick_save_path(Path("library.xlsx"), "xlsx"))

    assert window.kwargs["file_types"] == ("Excel files (*.xlsx)",)


def test_export_view__excel_hides_delimiter_and_encoding(tmp_path: Path) -> None:
    view = _view_at(tmp_path / "library.csv")
    assert view.file_type_select is not None

    view.file_type_select.value = "xlsx"

    assert view.options.file_type == "xlsx"
    assert view.path == tmp_path / "library.xlsx"
    assert "delimiter" not in view.option_widgets
    assert "encoding" not in view.option_widgets
    assert "max_length" not in view.option_widgets
    assert view.option_widgets["excel_max_length"].value == 32_767


def test_export_view__excel_keeps_delimiter_and_back_to_csv_shows_it(
    tmp_path: Path,
) -> None:
    view = _view_at(tmp_path / "library.csv")
    assert view.file_type_select is not None
    view.option_widgets["delimiter"].value = ";"

    view.file_type_select.value = "xlsx"
    assert view.options.delimiter == ";"
    view.file_type_select.value = "csv"

    assert view.options.delimiter == ","
    assert view.option_widgets["delimiter"].value == ","
    assert "excel_max_length" not in view.option_widgets


def test_export_view__excel_maximum_length_box_sets_its_own_option() -> None:
    changes: list[ExportOptions] = []
    view = _view(
        options=ExportOptions(file_type="xlsx"), on_options_change=changes.append
    )

    view.option_widgets["excel_max_length"].value = 100
    assert view.options.excel_max_length == 100
    assert view.options.max_length == 131_072
    assert changes[-1].excel_max_length == 100

    view.option_widgets["excel_max_length"].value = None
    assert view.options.excel_max_length == 32_767


def test_export_view__restore_defaults_resets_hidden_options() -> None:
    view = _view(
        options=ExportOptions(file_type="xlsx", delimiter=";", encoding="utf-8")
    )

    view._restore_options()

    assert view.options == ExportOptions()
    assert view.option_widgets["delimiter"].value == ","


def test_export_view__restore_defaults_resets_file_type(tmp_path: Path) -> None:
    view = _view_at(tmp_path / "library.csv")
    assert view.file_type_select is not None
    view.file_type_select.value = "tsv"

    view._restore_options()

    assert view.options == ExportOptions()
    assert view.path == tmp_path / "library.csv"


def test_export_view__chosen_path_shows_name_with_full_path_on_hover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    view = _view()
    for name in ("a.csv", "b.csv"):
        monkeypatch.setattr(
            export_flow.app.native, "main_window", _FakeWindow((str(tmp_path / name),))
        )
        run_in(view.middle, view._choose_path())

    assert view.path_label is not None
    assert view.path_label.text == str(Path(tmp_path.name) / "b.csv")
    assert _tooltip(view.path_label) == str(tmp_path / "b.csv")
    assert len(view.path_label.default_slot.children) == 1


def test_export_view__export_disabled_without_records() -> None:
    view = render_export_view(
        shell().middle,
        [],
        ExportOptions(),
        _DEFAULT_PATH,
        selected=False,
        on_export=lambda p, c, r, o: None,
    )

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
    assert columns == view.columns
    assert [record.id for record in records] == [1, 2]
    assert options == view.options


def test_export_view__all_columns_checked_by_default() -> None:
    view = _view()

    assert all(row.checkbox.value for row in view.rows)
    assert view.header_checkbox is not None
    assert view.header_checkbox.value is True


def test_export_view__unchecked_column_greyed_and_left_out_of_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, list[ExportColumn], list[ExportRecord], ExportOptions]] = []
    view = _view(on_export=lambda *args: calls.append(args))
    row = _row(view, "title")

    row.checkbox.value = False
    assert view.export_button is not None
    click_and_wait(view.export_button, monkeypatch)

    assert all("opacity-50" in cell.classes for cell in row.cells)
    assert view.header_checkbox is not None
    assert view.header_checkbox.value is None
    [(_, columns, _, _)] = calls
    assert "title" not in [column.key for column in columns]
    assert len(columns) == len(view.columns) - 1


def test_export_view__header_checkbox_toggles_all_and_disables_export() -> None:
    view = _view()
    assert view.header_checkbox is not None

    view.header_checkbox.value = False

    assert not any(row.checkbox.value for row in view.rows)
    assert view.export_button is not None
    assert view.export_button.enabled is False
    assert _tooltip(view.export_button) == "no columns selected"

    view.header_checkbox.value = True

    assert all(row.checkbox.value for row in view.rows)
    assert view.export_button.enabled is True


def test_export_view__unchecked_column_stays_unchecked_on_rebuild() -> None:
    view = _view()
    _row(view, "title").checkbox.value = False

    view.option_widgets["empty_columns"].value = True

    assert len(view.rows) > 2
    assert _row(view, "title").checkbox.value is False
    assert _row(view, "doi").checkbox.value is True


def test_export_view__maximum_length_box_sets_option_and_empty_restores_default() -> (
    None
):
    view = _view()

    view.option_widgets["max_length"].value = 32767
    assert view.options.max_length == 32767
    assert view.option_widgets["max_length"].props["bg-color"] == "blue-2"

    view.option_widgets["max_length"].value = None
    assert view.options.max_length == 131_072
