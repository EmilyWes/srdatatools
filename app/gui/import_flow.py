from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nicegui import app, ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.db.store import store_parsed_rows
from app.gui.csv_mapping import CsvMappingScreen, render_csv_mapping
from app.parsers.csv_ import ColumnMapping, parse_csv_file, read_csv_headers

_TYPE_UNKNOWN = "unknown"
_TYPE_CSV = "csv"
_TYPE_OPTIONS = {_TYPE_UNKNOWN: "Unknown", _TYPE_CSV: "CSV"}

_SOURCE_UNKNOWN = "unknown"
_SOURCE_OPTIONS = {_SOURCE_UNKNOWN: "Unknown"}


async def pick_file() -> Path | None:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(allow_multiple=False)
    return Path(selected[0]) if selected else None


def render_mapping(
    container: Element, file_type: str, path: Path
) -> CsvMappingScreen | None:
    if file_type != _TYPE_CSV:
        return None

    try:
        headers = read_csv_headers(path)
    except ValueError as exc:
        with container:
            ui.notify(str(exc), type="negative")
        return None

    if not headers:
        with container:
            ui.notify(f"{path.name} has no columns to map", type="negative")
        return None

    return render_csv_mapping(
        container, headers, lambda _m: None, show_confirm_button=False
    )


def import_csv(session: Session, path: Path, mapping: ColumnMapping) -> SourceFile:
    result = parse_csv_file(path, mapping)
    return store_parsed_rows(
        session,
        filename=path.name,
        path=str(path),
        format="csv",
        parsed_rows=[(row.record, row.raw_fields) for row in result.rows],
    )


def import_file(
    session: Session, path: Path, file_type: str, mapping: ColumnMapping
) -> SourceFile:
    if file_type != _TYPE_CSV:
        raise ValueError(f"unsupported file type: {file_type!r}")
    return import_csv(session, path, mapping)


@dataclass
class ImportView:
    middle: Element
    on_import: Callable[[Path, str, ColumnMapping], None]
    path: Path | None = None
    file_type: str = _TYPE_UNKNOWN
    mapping_screen: CsvMappingScreen | None = None
    import_button: ui.button | None = None
    stats_button: ui.button | None = None

    async def _select_file(self) -> None:
        picked = await pick_file()
        if picked is not None:
            self.path = picked
            self.render()

    def _set_type(self, file_type: str) -> None:
        self.file_type = file_type
        self.render()

    def _import(self) -> None:
        assert self.path is not None
        assert self.mapping_screen is not None
        self.on_import(self.path, self.file_type, self.mapping_screen.current_mapping())

    def _get_stats(self) -> None:
        ui.notify("Get stats is not implemented yet")

    def render(self) -> None:
        type_known = self.file_type != _TYPE_UNKNOWN
        has_file = self.path is not None

        self.middle.clear()
        with self.middle:
            with ui.column().classes("gap-4 pt-4 items-center w-full"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(
                        self.path.name if self.path else "No file selected"
                    ).classes("text-sm")
                    ui.button("Select file", on_click=self._select_file).props("dense")

                with ui.row().classes("items-center gap-2"):
                    ui.select(
                        _SOURCE_OPTIONS, value=_SOURCE_UNKNOWN, label="Source"
                    ).props("dense outlined").classes("w-48")

                    type_select = (
                        ui.select(_TYPE_OPTIONS, value=self.file_type, label="Type")
                        .props("dense outlined")
                        .classes("w-48")
                    )
                    type_select.on_value_change(lambda e: self._set_type(e.value))

                mapping_container = ui.column().classes("items-center w-full")
                if self.path is not None:
                    self.mapping_screen = render_mapping(
                        mapping_container, self.file_type, self.path
                    )
                else:
                    self.mapping_screen = None
                has_mapping = self.mapping_screen is not None

                with ui.row().classes("items-center gap-2"):
                    self.import_button = ui.button(
                        "Import", on_click=self._import
                    ).props("dense")
                    self.import_button.set_enabled(
                        has_file and type_known and has_mapping
                    )
                    if not type_known:
                        self.import_button.tooltip("please select the type")
                    elif not has_mapping:
                        self.import_button.tooltip("file has no mapping available")

                    self.stats_button = ui.button(
                        "Get stats", on_click=self._get_stats
                    ).props("dense")
                    self.stats_button.set_enabled(type_known)
                    if not type_known:
                        self.stats_button.tooltip("please select the type")


def render_import_view(
    middle: Element, on_import: Callable[[Path, str, ColumnMapping], None]
) -> ImportView:
    view = ImportView(middle=middle, on_import=on_import)
    view.render()
    return view
