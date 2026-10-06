from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nicegui import app, ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.db.store import store_parsed_rows
from app.gui.mapping_table import MappingScreen, render_mapping_table
from app.parsers.common import ParseResult
from app.parsers.csv_ import parse_csv_file, read_csv_headers, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.nbib import parse_nbib_file, read_nbib_tags, suggest_nbib_mapping
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping

_TYPE_UNKNOWN = "unknown"
_TYPE_RIS = "ris"
_TYPE_NBIB = "nbib"
_TYPE_CSV = "csv"
_TYPE_OPTIONS = {
    _TYPE_UNKNOWN: "Unknown",
    _TYPE_RIS: "RIS",
    _TYPE_NBIB: "NBIB",
    _TYPE_CSV: "CSV",
}

_SOURCE_UNKNOWN = "unknown"
_SOURCE_OPTIONS = {_SOURCE_UNKNOWN: "Unknown"}


async def pick_file() -> Path | None:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(allow_multiple=False)
    return Path(selected[0]) if selected else None


def render_mapping(
    container: Element, file_type: str, path: Path
) -> MappingScreen | None:
    read_keys: Callable[[Path], list[str]]
    suggest: Callable[[list[str]], FieldMapping]
    if file_type == _TYPE_CSV:
        read_keys, suggest, noun = read_csv_headers, suggest_mapping, "columns"
    elif file_type == _TYPE_RIS:
        read_keys, suggest, noun = read_ris_tags, suggest_ris_mapping, "tags"
    elif file_type == _TYPE_NBIB:
        read_keys, suggest, noun = read_nbib_tags, suggest_nbib_mapping, "tags"
    else:
        return None

    try:
        keys = read_keys(path)
    except ValueError as exc:
        with container:
            ui.notify(str(exc), type="negative")
        return None

    if not keys:
        with container:
            ui.notify(f"{path.name} has no {noun} to map", type="negative")
        return None

    return render_mapping_table(
        container, keys, suggest(keys), show_delimiter=file_type == _TYPE_CSV
    )


def _store(
    session: Session, path: Path, file_format: str, result: ParseResult
) -> SourceFile:
    return store_parsed_rows(
        session,
        filename=path.name,
        path=str(path),
        format=file_format,
        parsed_rows=[(row.record, row.raw_fields) for row in result.rows],
        skipped_rows=[(row.row_number, row.reason) for row in result.skipped],
    )


def import_csv(session: Session, path: Path, mapping: FieldMapping) -> SourceFile:
    return _store(session, path, _TYPE_CSV, parse_csv_file(path, mapping))


def import_ris(session: Session, path: Path, mapping: FieldMapping) -> SourceFile:
    return _store(session, path, _TYPE_RIS, parse_ris_file(path, mapping))


def import_nbib(session: Session, path: Path, mapping: FieldMapping) -> SourceFile:
    return _store(session, path, _TYPE_NBIB, parse_nbib_file(path, mapping))


def import_file(
    session: Session, path: Path, file_type: str, mapping: FieldMapping
) -> SourceFile:
    if file_type == _TYPE_CSV:
        return import_csv(session, path, mapping)
    if file_type == _TYPE_RIS:
        return import_ris(session, path, mapping)
    if file_type == _TYPE_NBIB:
        return import_nbib(session, path, mapping)
    raise ValueError(f"unsupported file type: {file_type!r}")


@dataclass
class ImportView:
    middle: Element
    on_import: Callable[[Path, str, FieldMapping], None]
    path: Path | None = None
    file_type: str = _TYPE_UNKNOWN
    mapping_screen: MappingScreen | None = None
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
    middle: Element, on_import: Callable[[Path, str, FieldMapping], None]
) -> ImportView:
    view = ImportView(middle=middle, on_import=on_import)
    view.render()
    return view
