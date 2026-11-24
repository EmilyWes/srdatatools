import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nicegui import app, ui
from nicegui.element import Element
from webview import FileDialog

from app.gui.export.columns import (
    NOTE_TAG,
    AuthorIdKeyColumn,
    DateColumn,
    ExportColumn,
    ExportRecord,
    JoinedColumn,
    KeywordsColumn,
    RisTypeColumn,
    default_note_name,
    example,
    export_columns,
    fill_count,
)
from app.gui.export.options import ExportFileType, ExportOptions, default_path
from app.gui.export.ris_tags import CURATED_TAGS, RIS_TAGS, TAG_PATTERN
from app.gui.importing.import_flow import (
    BUTTON_PROPS,
    FILE_LABEL_CLASSES,
    SELECT_CLASSES,
    SELECT_PROPS,
)
from app.helpers.format import GRID_CLASSES, GRID_COLUMNS, format_count
from app.helpers.mapping_table import ROW_FIELD_CSS, fill_color
from app.helpers.quirks_overview import (
    FIELD_CSS,
    render_box_frame,
    render_boxes_row,
    render_view_toggle,
)

OnExport = Callable[
    [Path, list[ExportColumn], list[ExportRecord], ExportOptions],
    Awaitable[None] | None,
]

_FILE_TYPES: dict[ExportFileType, str] = {
    "csv": "CSV files (*.csv)",
    "tsv": "TSV files (*.tsv)",
    "xlsx": "Excel files (*.xlsx)",
    "ris": "RIS files (*.ris)",
}
_TYPE_OPTIONS = {"csv": "CSV", "tsv": "TSV", "xlsx": "Excel", "ris": "RIS"}
_EXCEL_MAX_LENGTH = 32_767
_NO_RECORDS = "no records to export"
_NO_COLUMNS = "no columns selected"
_INVALID_TAGS = "invalid tag for: "
_UNCHECKED_CLASS = "opacity-50"

_EMPTY_NAME_COLOR = "red-2"
_SHARED_TAG_COLOR = "amber-2"
_CHANGED_COLOR = "blue-2"
_CHANGED_CHECKBOX_COLOR = "blue"
_OPTION_ROW_CLASSES = "w-full no-wrap items-center gap-1"
_OPTION_LABEL_CLASSES = "w-10 shrink-0 text-xs text-grey-7"
_NAME_WIDTH = "width: 24ch"
_FIELD_WIDTH = "width: 20ch"
_BOX_FIELD_CLASSES = "quirk-field text-xs"
_BOX_FIELD_WIDTH = "w-[6.5rem]"
_WIDE_BOX_FIELD_WIDTH = "w-[9rem]"
# Controls sit at the right edge of the (equally wide) boxes.
_BOX_GRID_STYLE = "grid-template-columns: max-content 1fr"

_DATE_PARTS = {"full": "Full date", "year": "Year", "month": "Month", "day": "Day"}

_DELIMITERS = {",": "Comma", ";": "Semicolon", "\t": "Tab"}
_ENCODINGS = {"utf-8-sig": "UTF-8 with BOM", "utf-8": "UTF-8"}
_LABEL_FORMATS = {"numbers": "Numbers", "words": "Words"}
_LINE_BREAKS = {"keep": "Keep", "space": "Replace with a space"}

_TAG_SEPARATOR = " — "
_TAG_OPTIONS = {
    tag: f"{tag}{_TAG_SEPARATOR}{meaning}" for tag, meaning in RIS_TAGS.items()
}
# NiceGUI hands Quasar each option as {value: index, label}, so the slots read
# the tag from the label; a typed tag is its own label.
_TAG_OF_OPTION = f"props.opt.label.split({json.dumps(_TAG_SEPARATOR)})[0]"
_TAG_OPTION_SLOT = (
    '<q-item v-bind="props.itemProps">'
    '<q-item-section side style="min-width: 1.5rem">'
    f"<q-icon v-if='{json.dumps(list(CURATED_TAGS))}.includes({_TAG_OF_OPTION})'"
    ' name="star" size="xs" color="amber">'
    "<q-tooltip>Commonly used; most reference managers read this tag</q-tooltip>"
    "</q-icon></q-item-section>"
    "<q-item-section>{{ props.opt.label }}</q-item-section>"
    "</q-item>"
    f"<q-separator v-if='{_TAG_OF_OPTION} === \"{list(CURATED_TAGS)[-1]}\"' />"
)
_TAG_SELECTED_SLOT = f"{{{{ {_TAG_OF_OPTION} }}}}"
_TYPE_TAG_HOVER = "Every RIS record starts with its type."


def _tag_options(tag: str) -> dict[str, str]:
    if tag and tag not in _TAG_OPTIONS:
        return {**_TAG_OPTIONS, tag: tag}
    return dict(_TAG_OPTIONS)


def _default_unchecked(columns: Sequence[ExportColumn]) -> set[str]:
    return {column.key for column in columns if not column.default_checked}


async def pick_save_path(suggested: Path, file_type: ExportFileType) -> Path | None:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(
        FileDialog.SAVE,
        directory=str(suggested.parent),
        save_filename=suggested.name,
        file_types=(_FILE_TYPES[file_type],),
    )
    return Path(selected[0]) if selected else None


@dataclass
class _Row:
    column: ExportColumn
    default_name: str
    checkbox: ui.checkbox
    # A RIS tag select; None for the fixed TY row.
    name: ui.input | ui.select | None
    count: ui.linear_progress
    example: ui.label
    # Greyed out while the column is unchecked.
    cells: list[Element]
    options: ui.column
    shared_tooltip: ui.tooltip | None = None


@dataclass
class ExportView:
    middle: Element
    records: list[ExportRecord]
    selected: bool
    options: ExportOptions
    path: Path
    on_export: OnExport
    on_options_change: Callable[[ExportOptions], Any] | None = None
    on_restore_options: Callable[[], Any] | None = None
    columns: list[ExportColumn] = field(default_factory=list)
    rows: list[_Row] = field(default_factory=list)
    option_widgets: dict[str, ui.select | ui.checkbox | ui.number] = field(
        default_factory=dict
    )
    mapping: ui.column | None = None
    option_boxes: Element | None = None
    path_label: ui.label | None = None
    path_chosen: bool = False
    file_type_select: ui.select | None = None
    export_button: ui.button | None = None
    header_checkbox: ui.checkbox | None = None
    # Keys of the unchecked columns; kept when the rows are rebuilt.
    unchecked: set[str] = field(default_factory=set)
    syncing_header: bool = False

    def __post_init__(self) -> None:
        self.columns = export_columns(self.records, self.options)
        self.unchecked = _default_unchecked(self.columns)

    @property
    def _ris(self) -> bool:
        return self.options.file_type == "ris"

    def _rebuild_columns(self) -> None:
        """Rows that stay keep their edited name and options."""
        current = {column.key: column for column in self.columns}
        fresh = export_columns(self.records, self.options)
        self.unchecked |= _default_unchecked(
            [column for column in fresh if column.key not in current]
        )
        self.columns = [current.get(column.key, column) for column in fresh]

    def _reset_columns(self) -> None:
        """Back to the file type's default names and checks."""
        self.columns = export_columns(self.records, self.options)
        self.unchecked = _default_unchecked(self.columns)
        self._render_mapping()

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

    def _valid_name(self, name: str) -> bool:
        return bool(TAG_PATTERN.fullmatch(name)) if self._ris else bool(name)

    def _shared_with(self, row: _Row) -> list[str]:
        """Other checked rows on the same RIS tag; N1 rows are told apart by their
        names."""
        column = row.column
        if not self._ris or column.name == NOTE_TAG or column.key in self.unchecked:
            return []
        return [
            other.column.label
            for other in self.rows
            if other is not row
            and other.column.key not in self.unchecked
            and other.column.name == column.name
        ]

    def _refresh_name_color(self, row: _Row) -> None:
        if row.name is None:
            return
        shared = self._shared_with(row)
        if not self._valid_name(row.column.name):
            row.name.props(f"bg-color={_EMPTY_NAME_COLOR}")
        elif shared:
            row.name.props(f"bg-color={_SHARED_TAG_COLOR}")
        elif row.column.name != row.default_name:
            row.name.props(f"bg-color={_CHANGED_COLOR}")
        else:
            row.name.props(remove="bg-color")
        if row.shared_tooltip is not None:
            row.shared_tooltip.set_text("Also used by: " + ", ".join(shared))
            row.shared_tooltip.set_visibility(bool(shared))

    def _refresh_name_colors(self) -> None:
        for row in self.rows:
            self._refresh_name_color(row)

    def _exported_columns(self) -> list[ExportColumn]:
        return [c for c in self.columns if c.key not in self.unchecked]

    def _optional_columns(self) -> list[ExportColumn]:
        """The TY row is always exported, so it isn't counted as a choice."""
        return [c for c in self.columns if not isinstance(c, RisTypeColumn)]

    def _set_checked(self, row: _Row, checked: bool) -> None:
        if checked:
            self.unchecked.discard(row.column.key)
        else:
            self.unchecked.add(row.column.key)
        self._refresh_checked(row)
        self._sync_header_checkbox()
        self._refresh_name_colors()
        self._refresh_export_button()

    def _refresh_checked(self, row: _Row) -> None:
        for cell in row.cells:
            if row.column.key in self.unchecked:
                cell.classes(add=_UNCHECKED_CLASS)
            else:
                cell.classes(remove=_UNCHECKED_CLASS)

    def _set_all_checked(self, value: bool | None) -> None:
        if self.syncing_header:
            return
        for row in self.rows:
            if not isinstance(row.column, RisTypeColumn):
                row.checkbox.value = value is not False

    def _sync_header_checkbox(self) -> None:
        """Partly checked shows as indeterminate (None)."""
        assert self.header_checkbox is not None
        optional = self._optional_columns()
        exported = sum(column.key not in self.unchecked for column in optional)
        value = True if exported == len(optional) else False if not exported else None
        self.syncing_header = True
        self.header_checkbox.value = value
        self.syncing_header = False

    def _set_tag(self, row: _Row, value: str | None) -> None:
        """A typed tag is uppercased, and a typed option dropped again: NiceGUI adds
        it to the select's options, replacing the label when it is a known tag."""
        assert isinstance(row.name, ui.select)
        tag = (value or "").strip().upper()
        if (value or None) != (tag or None):
            row.name.set_options({**_tag_options(tag), value: value})
            row.name.value = tag or None
            return
        if row.name.options != _tag_options(tag):
            row.name.set_options(_tag_options(tag))
        self._set_name(row, tag)

    def _set_name(self, row: _Row, value: str) -> None:
        previous = row.column.name
        row.column.name = value.strip()
        if self._ris and (row.column.name == NOTE_TAG) != (previous == NOTE_TAG):
            if row.column.name == NOTE_TAG:
                row.column.note_name = default_note_name(row.column)
            row.options.clear()
            with row.options:
                self._render_options(row)
        self._refresh_name_colors()
        self._refresh_export_button()

    def _set_column_option(self, row: _Row, name: str, value: str) -> None:
        setattr(row.column, name, value)
        self._refresh_row(row)

    def _option(
        self,
        row: _Row,
        name: str,
        short: str,
        label: str,
        choices: dict[str, str] | None = None,
    ) -> None:
        with ui.row().classes(_OPTION_ROW_CLASSES):
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

    def _render_options(self, row: _Row) -> None:
        column = row.column
        joined = not (self._ris and self.options.one_line_per_value)
        if isinstance(column, DateColumn) and not self._ris:
            self._option(row, "part", "part", "Part", _DATE_PARTS)
        elif (
            isinstance(column, AuthorIdKeyColumn | JoinedColumn | KeywordsColumn)
            and joined
        ):
            self._option(row, "delimiter", "sep", "Delimiter")
        if self._ris and column.name == NOTE_TAG:
            self._option(
                row, "note_name", "name", "Written before the value, as Name: value"
            )

    def _tag_select(self, column: ExportColumn) -> ui.select:
        select = ui.select(
            _tag_options(column.name),
            value=column.name or None,
            new_value_mode="add-unique",
            clearable=True,
        )
        # Shows the selected tag beside the search input rather than its label in it.
        select.props(remove="hide-selected fill-input")
        select.add_slot("option", _TAG_OPTION_SLOT)
        select.add_slot("selected-item", _TAG_SELECTED_SLOT)
        return select

    def _render_mapping(self) -> None:
        assert self.mapping is not None
        defaults = {c.key: c.name for c in export_columns(self.records, self.options)}
        self.rows = []
        self.mapping.clear()
        count_cell_classes = "self-stretch flex items-center px-2 mr-1"
        count_cell_style = "background: rgba(0, 0, 0, 0.04)"
        row_base = (
            "w-full min-w-max no-wrap items-center gap-1 pl-0 border-b outline-variant"
        )
        with self.mapping:
            with ui.column().classes("gap-0 border outline-variant rounded-xl"):
                with ui.row().classes(f"{row_base} py-2 surface-container"):
                    self.header_checkbox = ui.checkbox(
                        on_change=lambda e: self._set_all_checked(e.value)
                    ).props("dense")
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
                        row_classes += " surface-low"
                    with ui.row().classes(row_classes):
                        checkbox = ui.checkbox(
                            value=column.key not in self.unchecked
                        ).props("dense")
                        with (
                            ui.element("div")
                            .classes(count_cell_classes)
                            .style(count_cell_style)
                        ) as count_cell:
                            count = ui.linear_progress(show_value=False).classes("w-10")
                        field_label = (
                            ui.label(column.label)
                            .classes("truncate text-xs")
                            .style(_FIELD_WIDTH)
                            .tooltip(column.label)
                        )
                        with (
                            ui.column().classes("gap-0").style(_NAME_WIDTH) as name_cell
                        ):
                            name: ui.input | ui.select | None = None
                            shared_tooltip = None
                            if isinstance(column, RisTypeColumn):
                                checkbox.disable()
                                ui.label(column.name).classes("text-xs px-3").tooltip(
                                    _TYPE_TAG_HOVER
                                )
                            elif self._ris:
                                name = self._tag_select(column)
                                with name:
                                    shared_tooltip = ui.tooltip()
                            else:
                                name = ui.input(value=column.name)
                            if name is not None:
                                name.classes("mapping-field text-xs w-full").props(
                                    "dense outlined"
                                )
                            options = ui.column().classes("gap-0 w-full")
                        sample = ui.label().classes("w-48 truncate text-xs text-grey-7")
                    row = _Row(
                        column=column,
                        default_name=defaults[column.key],
                        checkbox=checkbox,
                        name=name,
                        count=count,
                        example=sample,
                        cells=[count_cell, field_label, name_cell, sample],
                        options=options,
                        shared_tooltip=shared_tooltip,
                    )
                    self.rows.append(row)
                    with options:
                        self._render_options(row)
                    if isinstance(name, ui.select):
                        name.on_value_change(
                            lambda e, row=row: self._set_tag(row, e.value)
                        )
                    elif name is not None:
                        name.on_value_change(
                            lambda e, row=row: self._set_name(row, e.value)
                        )
                    checkbox.on_value_change(
                        lambda e, row=row: self._set_checked(row, e.value)
                    )
                    self._refresh_row(row)
                    self._refresh_checked(row)
        self._refresh_name_colors()
        self._sync_header_checkbox()

    def _set_option(self, key: str, value: Any) -> None:
        if key in ("max_length", "excel_max_length"):
            # An emptied box falls back to the default.
            value = int(value) if value else getattr(ExportOptions(), key)
        previous = self.options.file_type
        self.options = self.options.model_copy(update={key: value})
        self._refresh_option_colors()
        if key == "file_type":
            self._change_file_type(value, previous)
        elif key in (
            "ignored_columns",
            "original_data",
            "empty_columns",
            "split_pages",
        ):
            self._rebuild_columns()
            self._render_mapping()
        elif key == "one_line_per_value":
            self._render_mapping()
        elif key in ("label_format", "cleaned_dates_only"):
            for row in self.rows:
                self._refresh_row(row)
        if self.on_options_change is not None:
            self.on_options_change(self.options)

    def _change_file_type(
        self, file_type: ExportFileType, previous: ExportFileType
    ) -> None:
        """A chosen path keeps its name; the default is worked out again. Switching
        to or from RIS starts the rows over, as tags and headers don't carry over."""
        if self.path_chosen:
            self.path = self.path.with_suffix(f".{file_type}")
        else:
            self.path = default_path(self.path.parent, file_type)
        self._show_path()
        if file_type in ("csv", "tsv"):
            delimiter = "\t" if file_type == "tsv" else ","
            self.options = self.options.model_copy(update={"delimiter": delimiter})
        if (file_type == "ris") != (previous == "ris"):
            self._reset_columns()
        self._render_option_boxes()

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
        self,
        key: str,
        label: str,
        hover: str,
        choices: dict[str, str] | None = None,
        maximum: int | None = None,
        wide: bool = False,
    ) -> None:
        with ui.label(label).classes("text-xs"):
            ui.tooltip(hover).classes("max-w-sm text-xs")
        value = getattr(self.options, key)
        widget: ui.select | ui.checkbox | ui.number
        if isinstance(value, bool):
            widget = ui.checkbox(value=value).props("dense keep-color size=32px")
        elif isinstance(value, int):
            widget = ui.number(value=value, min=1, max=maximum, precision=0)
            widget.props("dense outlined")
        else:
            widget = ui.select(choices or {}, value=value)
            widget.props("dense options-dense outlined")
        if not isinstance(widget, ui.checkbox):
            width = _WIDE_BOX_FIELD_WIDTH if wide else _BOX_FIELD_WIDTH
            widget.classes(f"{_BOX_FIELD_CLASSES} {width}")
        widget.classes("justify-self-end")
        widget.on_value_change(lambda e: self._set_option(key, e.value))
        self.option_widgets[key] = widget

    def _render_option_boxes(self) -> None:
        """Rendered again on a File type change, as Excel and RIS show other File
        and Values options."""
        assert self.option_boxes is not None
        excel = self.options.file_type == "xlsx"
        self.option_widgets = {}
        self.option_boxes.clear()
        with self.option_boxes, ui.column().classes("gap-1 w-full"):
            with render_boxes_row():
                with render_box_frame("File").style(_BOX_GRID_STYLE):
                    if excel:
                        self._box_item(
                            "excel_max_length",
                            "Maximum length",
                            "Longest value written, in characters; longer values"
                            " are cut. Excel holds at most 32.767 characters per"
                            " cell.",
                            maximum=_EXCEL_MAX_LENGTH,
                        )
                    elif self._ris:
                        self._box_item(
                            "ris_encoding",
                            "Encoding",
                            "Some RIS readers don't expect a BOM before the first"
                            " tag.",
                            _ENCODINGS,
                        )
                    else:
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
                            "Longest value written, in characters; longer values"
                            " are cut. 131.072 is the default limit of Python's CSV"
                            " reader, which many tools use; Excel holds at most"
                            " 32.767 characters per cell.",
                        )
                with render_box_frame("Values").style(_BOX_GRID_STYLE):
                    self._box_item(
                        "label_format",
                        "Label values",
                        "Numbers writes 1 / 0 / 0.5 / ?, Words writes include /"
                        " exclude / maybe / unknown; unlabeled is empty in both.",
                        _LABEL_FORMATS,
                    )
                    if self._ris:
                        self._box_item(
                            "one_line_per_value",
                            "One line per value",
                            "Writes each author, keyword, ISSN, label, … and each"
                            " line of the notes on a tag line of its own, as RIS"
                            " readers expect. Off joins them on one line with the"
                            " row's delimiter.",
                        )
                        self._box_item(
                            "split_pages",
                            "Split pages into SP / EP",
                            "Writes the start page to SP and the end page to EP."
                            " Off writes the whole range to SP.",
                        )
                        self._box_item(
                            "cleaned_dates_only",
                            "Only export cleaned dates",
                            "Writes only dates Cleaning turned into YYYY/MM/DD to"
                            " DA. Off writes other dates as stored.",
                        )
                    else:
                        self._box_item(
                            "line_breaks",
                            "Line breaks",
                            "Line breaks inside a value (e.g. an abstract) are kept"
                            + (" in the cell" if excel else " within quotes")
                            + ", or replaced with a space.",
                            _LINE_BREAKS,
                            wide=True,
                        )
                with render_box_frame("Column selection").style(_BOX_GRID_STYLE):
                    self._box_item(
                        "empty_columns",
                        "Export empty columns",
                        "Adds the columns that none of the exported records has a"
                        " value for.",
                    )
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
        """Resets the options model itself, as the File options of the other file
        types have no widgets."""
        previous = self.options.file_type
        self.options = ExportOptions()
        assert self.file_type_select is not None
        self.file_type_select.value = self.options.file_type
        self._change_file_type(self.options.file_type, previous)
        self._rebuild_columns()
        self._render_mapping()
        if self.on_restore_options is not None:
            self.on_restore_options()

    async def _choose_path(self) -> None:
        path = await pick_save_path(self.path, self.options.file_type)
        if path is None:
            return
        self.path = path
        self.path_chosen = True
        self._show_path()

    def _show_path(self) -> None:
        assert self.path_label is not None
        self.path_label.set_text(str(Path(self.path.parent.name) / self.path.name))
        self.path_label.clear()
        with self.path_label:
            ui.tooltip(str(self.path))

    def _records_noun(self) -> str:
        noun = "record" if len(self.records) == 1 else "records"
        return f"selected {noun}" if self.selected else noun

    def _refresh_export_button(self) -> None:
        if self.export_button is None:
            return
        exported = self._exported_columns()
        invalid = [c.label for c in exported if not self._valid_name(c.name)]
        reason = None
        if not self.records:
            reason = _NO_RECORDS
        elif all(c.key in self.unchecked for c in self._optional_columns()):
            reason = _NO_COLUMNS
        elif self._ris and invalid:
            reason = _INVALID_TAGS + ", ".join(invalid)
        self.export_button.set_enabled(reason is None)
        self.export_button.clear()
        if reason is not None:
            with self.export_button:
                ui.tooltip(reason)

    def _export(self) -> Awaitable[None] | None:
        return self.on_export(
            self.path, self._exported_columns(), self.records, self.options
        )

    def render(self) -> None:
        ui.add_css(ROW_FIELD_CSS)
        ui.add_css(FIELD_CSS)
        self.middle.clear()
        with self.middle:
            with ui.column().classes("gap-4 pt-4 items-center w-full"):
                with ui.grid(columns=GRID_COLUMNS).classes(GRID_CLASSES):
                    with ui.row().classes(
                        "col-span-2 justify-self-center gap-1 text-sm"
                    ):
                        ui.label("Exporting")
                        ui.label(format_count(len(self.records))).classes("font-bold")
                        ui.label(self._records_noun() + " to:")
                    ui.label("File type:").classes("text-sm")
                    self.file_type_select = (
                        ui.select(_TYPE_OPTIONS, value=self.options.file_type)
                        .props(SELECT_PROPS)
                        .classes(SELECT_CLASSES)
                    )
                    self.file_type_select.on_value_change(
                        lambda e: self._set_option("file_type", e.value)
                    )
                    ui.button("Select file path…", on_click=self._choose_path).props(
                        BUTTON_PROPS
                    )
                    self.path_label = ui.label().classes(FILE_LABEL_CLASSES)
                    self._show_path()
                views = render_view_toggle(parsing_label="Options")
                self.mapping = views.mapping
                self._render_mapping()
                self.option_boxes = views.parsing
                self._render_option_boxes()
                self.export_button = ui.button("Export", on_click=self._export).props(
                    "dense"
                )
                self._refresh_export_button()


def render_export_view(
    middle: Element,
    records: list[ExportRecord],
    options: ExportOptions,
    path: Path,
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
        path=path,
        on_export=on_export,
        on_options_change=on_options_change,
        on_restore_options=on_restore_options,
    )
    view.render()
    return view
