import asyncio
from pathlib import Path
from typing import Any

import pytest
from nicegui import ui
from nicegui.element import Element
from nicegui.elements.tooltip import Tooltip

from app.gui.export import export_flow
from app.gui.export.export_flow import ExportView, pick_save_path, render_export_view
from app.gui.export.mapping import (
    ExportField,
    ExportRecord,
    ExportSource,
    RisTypeField,
)
from app.gui.export.options import ExportOptions
from app.gui.general.layout import shell
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
                author_names=["LeCun, Yann"],
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

    assert [_row(view, c.key).name.value for c in view.columns] == [
        c.name for c in view.columns
    ]
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

    view.screen.widgets["original_data"].value = True

    keys = [row.column.key for row in view.rows]
    assert keys[-2:] == ["raw:Title", "raw:Link"]
    assert _row(view, "raw:Title").name.value == "Title (original)"
    assert _row(view, "title").name.value == "TI"
    assert view.screen.widgets["ignored_columns"].enabled is False
    assert changes[-1].original_data is True


def test_export_view__empty_columns_option_adds_empty_rows() -> None:
    view = _view()
    assert "abstract" not in [row.column.key for row in view.rows]

    view.screen.widgets["empty_columns"].value = True

    assert "abstract" in [row.column.key for row in view.rows]


def test_export_view__ignored_columns_adds_only_ignored_raw_rows() -> None:
    view = _view()

    view.screen.widgets["ignored_columns"].value = True

    raw_keys = [r.column.key for r in view.rows if r.column.key.startswith("raw:")]
    assert raw_keys == ["raw:Link"]


def test_export_view__restore_defaults_resets_shown_options_and_saves() -> None:
    changes: list[ExportOptions] = []
    view = _view(
        options=ExportOptions(delimiter=";", original_data=True),
        on_options_change=changes.append,
    )

    view.screen.restore_defaults()

    assert view.options == ExportOptions()
    assert changes[-1] == ExportOptions()
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
    assert "delimiter" not in view.screen.widgets
    assert "encoding" not in view.screen.widgets
    assert "max_length" not in view.screen.widgets
    assert view.screen.widgets["excel_max_length"].value == 32_767


def test_export_view__excel_keeps_delimiter_and_back_to_csv_shows_it(
    tmp_path: Path,
) -> None:
    view = _view_at(tmp_path / "library.csv")
    assert view.file_type_select is not None
    view.screen.widgets["delimiter"].value = ";"

    view.file_type_select.value = "xlsx"
    assert view.options.delimiter == ";"
    view.file_type_select.value = "csv"

    assert view.options.delimiter == ","
    assert view.screen.widgets["delimiter"].value == ","
    assert "excel_max_length" not in view.screen.widgets


def test_export_view__excel_maximum_length_box_sets_its_own_option() -> None:
    changes: list[ExportOptions] = []
    view = _view(
        options=ExportOptions(file_type="xlsx"), on_options_change=changes.append
    )

    view.screen.widgets["excel_max_length"].value = 100
    assert view.options.excel_max_length == 100
    assert view.options.max_length == 131_072
    assert changes[-1].excel_max_length == 100

    view.screen.widgets["excel_max_length"].value = None
    assert view.options.excel_max_length == 32_767


def test_export_view__restore_defaults_keeps_file_type_and_hidden_options() -> None:
    view = _view(
        options=ExportOptions(file_type="xlsx", delimiter=";", excel_max_length=100)
    )

    view.screen.restore_defaults()

    assert view.options.file_type == "xlsx"
    assert view.options.delimiter == ";"
    assert view.options.excel_max_length == 32_767


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
    calls: list[tuple[Path, list[ExportField], list[ExportRecord], ExportOptions]] = []
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
    calls: list[tuple[Path, list[ExportField], list[ExportRecord], ExportOptions]] = []
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

    view.screen.widgets["empty_columns"].value = True

    assert len(view.rows) > 2
    assert _row(view, "title").checkbox.value is False
    assert _row(view, "doi").checkbox.value is True


def test_export_view__maximum_length_box_sets_option_and_empty_restores_default() -> (
    None
):
    view = _view()

    view.screen.widgets["max_length"].value = 32767
    assert view.options.max_length == 32767
    assert view.screen.widgets["max_length"].props["bg-color"] == "blue-2"

    view.screen.widgets["max_length"].value = None
    assert view.options.max_length == 131_072


_RIS = ExportOptions(file_type="ris")


def _ris_view(options: ExportOptions = _RIS, **callbacks: Any) -> ExportView:
    return _view(options=options, **callbacks)


def _type_tag(row: Any, typed: str) -> None:
    """As NiceGUI does for a value typed into the select."""
    row.name.set_options({**row.name.options, typed: typed})
    row.name.value = typed


def test_export_view__ris_rows_have_tag_selects_with_default_tags() -> None:
    view = _ris_view()

    title = _row(view, "title")
    assert isinstance(title.name, ui.select)
    assert title.name.value == "TI"
    assert isinstance(title.name.options, dict)
    assert title.name.options["TI"] == "TI — Title"


def test_export_view__ris_type_row_first_fixed_and_locked() -> None:
    view = _ris_view()

    row = view.rows[0]
    assert isinstance(row.column, RisTypeField)
    assert row.name is None
    assert row.checkbox.value is True
    assert row.checkbox.enabled is False


def test_export_view__ris_rows_without_a_tag_start_unchecked() -> None:
    view = _ris_view()

    assert _row(view, "sources").checkbox.value is False
    assert _row(view, "title").checkbox.value is True


def test_export_view__switching_to_and_from_ris_resets_names() -> None:
    view = _view()
    assert view.file_type_select is not None
    _row(view, "title").name.value = "My title"

    view.file_type_select.value = "ris"
    assert _row(view, "title").name.value == "TI"
    _type_tag(_row(view, "title"), "T1")
    view.file_type_select.value = "csv"

    assert _row(view, "title").name.value == "Title"
    assert _row(view, "sources").checkbox.value is True


def test_export_view__ris_typed_tag_is_uppercased() -> None:
    view = _ris_view()
    row = _row(view, "title")

    _type_tag(row, "t1")

    assert row.name.value == "T1"
    assert row.column.name == "T1"
    assert "t1" not in row.name.options
    assert row.name.props["bg-color"] == "blue-2"


def test_export_view__ris_typed_known_tag_keeps_its_label() -> None:
    view = _ris_view()
    row = _row(view, "title")

    _type_tag(row, "AB")

    assert row.name.options["AB"] == "AB — Abstract"


def test_export_view__ris_custom_tag_accepted() -> None:
    view = _ris_view()
    row = _row(view, "title")

    _type_tag(row, "Z9")

    assert row.column.name == "Z9"
    assert row.name.options["Z9"] == "Z9"
    assert view.export_button is not None
    assert view.export_button.enabled is True


def test_export_view__ris_invalid_tag_turns_red_and_disables_export() -> None:
    view = _ris_view()
    row = _row(view, "title")

    _type_tag(row, "title")

    assert row.name.props["bg-color"] == "red-2"
    assert view.export_button is not None
    assert view.export_button.enabled is False
    assert _tooltip(view.export_button) == "invalid tag for: Title"

    row.checkbox.value = False

    assert view.export_button.enabled is True


def test_export_view__ris_shared_tag_gets_warning_colour_and_hover() -> None:
    view = _ris_view()
    title, doi = _row(view, "title"), _row(view, "doi")

    _type_tag(doi, "TI")

    assert title.name.props["bg-color"] == "orange-2"
    assert doi.name.props["bg-color"] == "orange-2"
    assert title.shared_tooltip.text == "Also used by: DOI"
    assert title.shared_tooltip.visible is True

    doi.checkbox.value = False

    assert "bg-color" not in title.name.props
    assert title.shared_tooltip.visible is False


def test_export_view__ris_n1_rows_not_marked_as_shared() -> None:
    view = _ris_view()

    _type_tag(_row(view, "title"), "N1")
    _type_tag(_row(view, "doi"), "N1")

    assert _row(view, "title").name.props["bg-color"] == "blue-2"


def _option_inputs(row: Any) -> list[ui.input]:
    return [e for e in row.options.descendants() if isinstance(e, ui.input)]


def test_export_view__ris_n1_shows_name_box_starting_at_field_name() -> None:
    view = _ris_view()
    row = _row(view, "title")

    _type_tag(row, "N1")

    [name] = _option_inputs(row)
    assert name.value == "Title"
    name.value = ""
    assert row.column.note_name == ""

    _type_tag(row, "TI")

    assert _option_inputs(row) == []


def test_export_view__ris_one_line_per_value_hides_delimiter() -> None:
    view = _ris_view()
    assert _option_inputs(_row(view, "author_names")) == []

    view.screen.widgets["one_line_per_value"].value = False

    [delimiter] = _option_inputs(_row(view, "author_names"))
    assert delimiter.value == "; "


def test_export_view__ris_date_rows_have_no_part_option() -> None:
    view = _ris_view(ExportOptions(file_type="ris", empty_columns=True))

    assert list(_row(view, "date").options.descendants()) == []
    assert _row(view, "date:year").name.value == "PY"


def test_export_view__ris_split_pages_option_rebuilds_rows() -> None:
    view = _ris_view(ExportOptions(file_type="ris", empty_columns=True))
    assert _row(view, "pages:end").name.value == "EP"

    view.screen.widgets["split_pages"].value = False

    keys = [row.column.key for row in view.rows]
    assert "pages:end" not in keys
    assert _row(view, "pages").name.value == "SP"


def test_export_view__ris_options_hide_tabular_settings() -> None:
    view = _ris_view()

    assert {
        "ris_encoding",
        "label_format",
        "one_line_per_value",
        "split_pages",
        "cleaned_dates_only",
    } <= view.screen.widgets.keys()
    assert not {"delimiter", "encoding", "max_length", "line_breaks"} & (
        view.screen.widgets.keys()
    )


def test_export_view__ris_header_checkbox_leaves_type_row_checked() -> None:
    view = _ris_view()
    assert view.header_checkbox is not None

    view.header_checkbox.value = False

    assert view.rows[0].checkbox.value is True
    assert view.header_checkbox.value is False
    assert view.export_button is not None
    assert _tooltip(view.export_button) == "no columns selected"


def test_pick_save_path__ris_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _FakeWindow(None)
    monkeypatch.setattr(export_flow.app.native, "main_window", window)

    asyncio.run(pick_save_path(Path("library.ris"), "ris"))

    assert window.kwargs["file_types"] == ("RIS files (*.ris)",)
