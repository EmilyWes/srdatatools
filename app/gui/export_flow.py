from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nicegui import app, ui
from nicegui.element import Element
from webview import FileDialog

from app.export.columns import (
    AuthorsColumn,
    DateColumn,
    ExportColumn,
    ExportRecord,
    KeywordsColumn,
    example,
    export_columns,
    fill_count,
)
from app.export.options import ExportOptions
from app.gui.format import format_count
from app.gui.mapping_table import ROW_FIELD_CSS, fill_color
from app.gui.quirks_overview import (
    FIELD_CSS,
    VIEW_MAPPING,
    render_box_frame,
    render_view_toggle,
)

OnExport = Callable[
    [Path, list[ExportColumn], list[ExportRecord], ExportOptions],
    Awaitable[None] | None,
]

_DEFAULT_FILENAME = "library.csv"
_FILE_TYPES = ("CSV files (*.csv)",)
_TYPE_OPTIONS = {"csv": "CSV"}
_NO_PATH = "choose a target file"
_NO_RECORDS = "no records to export"

_EMPTY_NAME_COLOR = "red-2"
_CHANGED_COLOR = "blue-2"
_CHANGED_CHECKBOX_COLOR = "blue"
_OPTION_ROW_CLASSES = "w-full no-wrap items-center gap-1"
_OPTION_LABEL_CLASSES = "w-10 shrink-0 text-xs text-grey-7"
_NAME_WIDTH = "width: 24ch"
_FIELD_WIDTH = "width: 20ch"
_BOX_FIELD_CLASSES = "quirk-field text-xs w-[7rem]"

_AUTHOR_FORMATS = {
    "last_first": "Names: last, first",
    "first_last": "Names: first last",
    "full_name": "Full name",
}
_DATE_PARTS = {"full": "Full date", "year": "Year", "month": "Month", "day": "Day"}

_DELIMITERS = {",": "Comma", ";": "Semicolon", "\t": "Tab"}
_ENCODINGS = {"utf-8-sig": "UTF-8 with BOM", "utf-8": "UTF-8"}
_LABEL_FORMATS = {"numbers": "Numbers", "words": "Words"}
_LINE_BREAKS = {"keep": "Keep", "space": "Replace with a space"}


async def pick_save_path() -> Path | None:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(
        FileDialog.SAVE, save_filename=_DEFAULT_FILENAME, file_types=_FILE_TYPES
    )
    return Path(selected[0]) if selected else None


def _records_line(count: int, selected: bool) -> str:
    noun = "record" if count == 1 else "records"
    if selected:
        return f"Exporting {format_count(count)} selected {noun}"
    return f"Exporting all {format_count(count)} {noun}"


@dataclass
class _Row:
    column: ExportColumn
    default_name: str
    name: ui.input
    count: ui.linear_progress
    example: ui.label
    option_rows: dict[str, ui.row] = field(default_factory=dict)


@dataclass
class ExportView:
    middle: Element
    records: list[ExportRecord]
    selected: bool
    options: ExportOptions
    on_export: OnExport
    on_options_change: Callable[[ExportOptions], Any] | None = None
    on_restore_options: Callable[[], Any] | None = None
    path: Path | None = None
    columns: list[ExportColumn] = field(default_factory=list)
    rows: list[_Row] = field(default_factory=list)
    option_widgets: dict[str, ui.select | ui.checkbox | ui.number] = field(
        default_factory=dict
    )
    mapping: ui.column | None = None
    path_label: ui.label | None = None
    export_button: ui.button | None = None

    def __post_init__(self) -> None:
        self.columns = export_columns(self.records, self.options)

    def _rebuild_columns(self) -> None:
        """Rows that stay keep their edited name and options."""
        current = {column.key: column for column in self.columns}
        self.columns = [
            current.get(column.key, column)
            for column in export_columns(self.records, self.options)
        ]

    def _refresh_row(self, row: _Row) -> None:
        total = len(self.records)
        filled = fill_count(row.column, self.records, self.options)
        row.count.value = filled / total if total else 0.0
        row.count.props(f"color={fill_color(filled, total)}")
        row.count.clear()
        with row.count:
            ui.tooltip(f"{filled} of {total}")
        text = example(row.column, self.records, self.options)
        row.example.set_text(text)
        row.example.clear()
        if text:
            with row.example:
                ui.tooltip(text)

    def _refresh_name_color(self, row: _Row) -> None:
        if not row.column.name:
            row.name.props(f"bg-color={_EMPTY_NAME_COLOR}")
        elif row.column.name != row.default_name:
            row.name.props(f"bg-color={_CHANGED_COLOR}")
        else:
            row.name.props(remove="bg-color")

    def _set_name(self, row: _Row, value: str) -> None:
        row.column.name = value.strip()
        self._refresh_name_color(row)

    def _set_column_option(self, row: _Row, name: str, value: str) -> None:
        setattr(row.column, name, value)
        self._refresh_option_visibility(row)
        self._refresh_row(row)

    def _refresh_option_visibility(self, row: _Row) -> None:
        name_row = row.option_rows.get("name_separator")
        if name_row is not None and isinstance(row.column, AuthorsColumn):
            name_row.set_visibility(row.column.format == "last_first")

    def _option(
        self,
        row: _Row,
        name: str,
        short: str,
        label: str,
        choices: dict[str, str] | None = None,
    ) -> None:
        with ui.row().classes(_OPTION_ROW_CLASSES) as option_row:
            ui.label(f"{short}:").classes(_OPTION_LABEL_CLASSES).tooltip(label)
            value = getattr(row.column, name)
            widget: ui.select | ui.input
            if choices is not None:
                widget = ui.select(choices, value=value)
                widget.props("dense options-dense outlined")
            else:
                # Separators may be or end in a space, so they aren't stripped.
                widget = ui.input(value=value).props("dense outlined")
            widget.classes("mapping-field text-xs col")
            widget.on_value_change(
                lambda e: self._set_column_option(row, name, e.value or "")
            )
        row.option_rows[name] = option_row

    def _render_options(self, row: _Row) -> None:
        column = row.column
        if isinstance(column, AuthorsColumn):
            self._option(row, "format", "fmt", "Format", _AUTHOR_FORMATS)
            self._option(row, "name_separator", "name", "Name separator")
            self._option(row, "author_separator", "aut", "Author separator")
            self._refresh_option_visibility(row)
        elif isinstance(column, DateColumn):
            self._option(row, "part", "part", "Part", _DATE_PARTS)
        elif isinstance(column, KeywordsColumn):
            self._option(row, "delimiter", "sep", "Delimiter")

    def _render_mapping(self) -> None:
        assert self.mapping is not None
        defaults = {c.key: c.name for c in export_columns(self.records, self.options)}
        self.rows = []
        self.mapping.clear()
        count_cell_classes = "self-stretch flex items-center px-2 mr-1"
        count_cell_style = "background: rgba(0, 0, 0, 0.04)"
        row_base = "w-full min-w-max no-wrap items-center gap-1 pl-0 border-b"
        with self.mapping:
            with ui.column().classes("gap-0 border rounded-borders"):
                with ui.row().classes(f"{row_base} py-2 bg-grey-2"):
                    with (
                        ui.element("div")
                        .classes(count_cell_classes)
                        .style(count_cell_style)
                    ):
                        ui.label("#").classes("w-10 text-xs font-bold text-center")
                    ui.label("Field").classes("text-xs font-bold").style(_FIELD_WIDTH)
                    ui.label("Export as").classes("text-xs font-bold").style(
                        _NAME_WIDTH
                    )
                    ui.label("Example").classes("w-48 text-xs font-bold text-center")
                for i, column in enumerate(self.columns):
                    row_classes = f"{row_base} py-0"
                    if i % 2 == 1:
                        row_classes += " bg-grey-1"
                    with ui.row().classes(row_classes):
                        with (
                            ui.element("div")
                            .classes(count_cell_classes)
                            .style(count_cell_style)
                        ):
                            count = ui.linear_progress(show_value=False).classes("w-10")
                        ui.label(column.label).classes("truncate text-xs").style(
                            _FIELD_WIDTH
                        ).tooltip(column.label)
                        with ui.column().classes("gap-0").style(_NAME_WIDTH):
                            name = (
                                ui.input(value=column.name)
                                .classes("mapping-field text-xs w-full")
                                .props("dense outlined")
                            )
                            options = ui.column().classes("gap-0 w-full")
                        sample = ui.label().classes("w-48 truncate text-xs text-grey-7")
                    row = _Row(
                        column=column,
                        default_name=defaults[column.key],
                        name=name,
                        count=count,
                        example=sample,
                    )
                    self.rows.append(row)
                    with options:
                        self._render_options(row)
                    name.on_value_change(
                        lambda e, row=row: self._set_name(row, e.value)
                    )
                    self._refresh_name_color(row)
                    self._refresh_row(row)

    def _set_option(self, key: str, value: Any) -> None:
        if key == "max_length":
            # An emptied box falls back to the default.
            value = int(value) if value else ExportOptions().max_length
        self.options = self.options.model_copy(update={key: value})
        self._refresh_option_colors()
        if key in ("ignored_columns", "original_data", "empty_columns"):
            self._rebuild_columns()
            self._render_mapping()
        elif key == "label_format":
            for row in self.rows:
                self._refresh_row(row)
        if self.on_options_change is not None:
            self.on_options_change(self.options)

    def _refresh_option_colors(self) -> None:
        defaults = ExportOptions()
        for key, widget in self.option_widgets.items():
            changed = getattr(self.options, key) != getattr(defaults, key)
            if isinstance(widget, ui.checkbox):
                if changed:
                    widget.props(f"color={_CHANGED_CHECKBOX_COLOR}")
                else:
                    widget.props(remove="color")
            elif changed:
                widget.props(f"bg-color={_CHANGED_COLOR}")
            else:
                widget.props(remove="bg-color")
        ignored = self.option_widgets.get("ignored_columns")
        if ignored is not None:
            ignored.set_enabled(not self.options.original_data)

    def _box_item(
        self, key: str, label: str, hover: str, choices: dict[str, str] | None = None
    ) -> None:
        with ui.label(label).classes("text-xs"):
            ui.tooltip(hover).classes("max-w-sm text-xs")
        value = getattr(self.options, key)
        widget: ui.select | ui.checkbox | ui.number
        if isinstance(value, bool):
            widget = ui.checkbox(value=value).props("dense keep-color size=32px")
        elif isinstance(value, int):
            widget = ui.number(value=value, min=1, precision=0)
            widget.classes(_BOX_FIELD_CLASSES).props("dense outlined")
        else:
            widget = ui.select(choices or {}, value=value)
            widget.classes(_BOX_FIELD_CLASSES).props("dense options-dense outlined")
        widget.on_value_change(lambda e: self._set_option(key, e.value))
        self.option_widgets[key] = widget

    def _render_option_boxes(self, container: Element) -> None:
        self.option_widgets = {}
        container.clear()
        with container, ui.column().classes("gap-1 w-full"):
            with ui.row().classes("w-full items-start gap-3 pl-3"):
                with render_box_frame("File"):
                    self._box_item(
                        "delimiter",
                        "Delimiter",
                        "The character between the values in a row.",
                        _DELIMITERS,
                    )
                    self._box_item(
                        "encoding",
                        "Encoding",
                        "With a BOM, Excel shows accented characters correctly"
                        " when it opens the file.",
                        _ENCODINGS,
                    )
                    self._box_item(
                        "max_length",
                        "Maximum length",
                        "Longest value written, in characters; longer values are"
                        " cut. 131.072 is the default limit of Python's CSV reader,"
                        " which many tools use; Excel holds at most 32.767"
                        " characters per cell.",
                    )
                with render_box_frame("Values"):
                    self._box_item(
                        "label_format",
                        "Label values",
                        "Numbers writes 1 / 0 / 0.5 / ?, Words writes include /"
                        " exclude / maybe / unknown; unlabeled is empty in both.",
                        _LABEL_FORMATS,
                    )
                    self._box_item(
                        "line_breaks",
                        "Line breaks",
                        "Line breaks inside a value (e.g. an abstract) are kept"
                        " within quotes, or replaced with a space.",
                        _LINE_BREAKS,
                    )
                    self._box_item(
                        "empty_columns",
                        "Export empty columns",
                        "Adds the columns that none of the exported records has a"
                        " value for.",
                    )
                with render_box_frame("Original data"):
                    self._box_item(
                        "ignored_columns",
                        "Export ignored input columns",
                        "Adds a row for each input column or tag that was set to"
                        " ignore at import, with the value as it was imported.",
                    )
                    self._box_item(
                        "original_data",
                        "Export original data",
                        "Adds a row for every input column or tag, with the value"
                        " as it was imported.",
                    )
            with ui.row().classes("w-full justify-end"):
                ui.button("Restore defaults", on_click=self._restore_options).props(
                    "dense flat no-caps"
                ).classes("text-xs")
        self._refresh_option_colors()

    def _restore_options(self) -> None:
        for key, widget in self.option_widgets.items():
            widget.value = getattr(ExportOptions(), key)
        if self.on_restore_options is not None:
            self.on_restore_options()

    async def _choose_path(self) -> None:
        path = await pick_save_path()
        if path is None:
            return
        self.path = path
        assert self.path_label is not None
        self.path_label.set_text(str(path))
        self._refresh_export_button()

    def _refresh_export_button(self) -> None:
        assert self.export_button is not None
        self.export_button.set_enabled(bool(self.path and self.records))
        self.export_button.clear()
        reason = _NO_RECORDS if not self.records else None if self.path else _NO_PATH
        if reason is not None:
            with self.export_button:
                ui.tooltip(reason)

    def _export(self) -> Awaitable[None] | None:
        assert self.path is not None
        return self.on_export(self.path, self.columns, self.records, self.options)

    def render(self) -> None:
        ui.add_css(ROW_FIELD_CSS)
        ui.add_css(FIELD_CSS)
        self.middle.clear()
        with self.middle:
            with ui.column().classes("gap-4 pt-4 items-center w-full"):
                with ui.row().classes("items-center gap-2"):
                    self.path_label = ui.label("No file chosen").classes("text-sm")
                    ui.button("Save as…", on_click=self._choose_path).props("dense")
                ui.select(
                    _TYPE_OPTIONS, value=self.options.file_type, label="Type"
                ).props("dense outlined").classes("w-48")
                ui.label(_records_line(len(self.records), self.selected)).classes(
                    "text-sm text-grey-7"
                )
                views = render_view_toggle(VIEW_MAPPING, parsing_label="Options")
                self.mapping = views.mapping
                self._render_mapping()
                self._render_option_boxes(views.parsing)
                self.export_button = ui.button("Export", on_click=self._export).props(
                    "dense"
                )
                self._refresh_export_button()


def render_export_view(
    middle: Element,
    records: list[ExportRecord],
    options: ExportOptions,
    *,
    selected: bool,
    on_export: OnExport,
    on_options_change: Callable[[ExportOptions], Any] | None = None,
    on_restore_options: Callable[[], Any] | None = None,
) -> ExportView:
    view = ExportView(
        middle=middle,
        records=records,
        selected=selected,
        options=options,
        on_export=on_export,
        on_options_change=on_options_change,
        on_restore_options=on_restore_options,
    )
    view.render()
    return view
