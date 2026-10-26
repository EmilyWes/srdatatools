from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from nicegui import app, ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.db.store import store_parsed_rows
from app.gui.activity_log import log_import
from app.gui.mapping_table import MappingScreen, render_mapping_table
from app.models.record import Record
from app.parsers.bibtex import (
    parse_bibtex_file,
    parse_bibtex_record,
    read_bibtex_fields,
    suggest_bibtex_mapping,
)
from app.parsers.common import FileSummary, ParsedRow, ParseResult
from app.parsers.csv_ import (
    parse_csv_file,
    parse_csv_record,
    read_csv_headers,
    suggest_mapping,
)
from app.parsers.detect import detect_source, detect_type
from app.parsers.mapping import FieldMapping
from app.parsers.nbib import (
    parse_nbib_file,
    parse_nbib_record,
    read_nbib_tags,
    suggest_nbib_mapping,
)
from app.parsers.profiles import PROFILES, apply_profile, profile_for
from app.parsers.ris import (
    parse_ris_file,
    parse_ris_record,
    read_ris_tags,
    suggest_ris_mapping,
)

_TYPE_UNKNOWN = "unknown"
_TYPE_RIS = "ris"
_TYPE_NBIB = "nbib"
_TYPE_CSV = "csv"
_TYPE_BIBTEX = "bibtex"
_TYPE_OPTIONS = {
    _TYPE_UNKNOWN: "Unknown",
    _TYPE_RIS: "RIS",
    _TYPE_NBIB: "NBIB",
    _TYPE_CSV: "CSV",
    _TYPE_BIBTEX: "BibTeX",
}

_SOURCE_UNKNOWN = "unknown"
_SOURCE_OPTIONS = {
    _SOURCE_UNKNOWN: "Unknown",
    **{key: profile.label for key, profile in PROFILES.items()},
}


async def pick_file() -> Path | None:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(allow_multiple=False)
    return Path(selected[0]) if selected else None


def _parse_csv_lines(lines: list[tuple[str, str]], mapping: FieldMapping) -> ParsedRow:
    return parse_csv_record(dict(lines), mapping)


def render_mapping(
    container: Element, file_type: str, path: Path, source: str = _SOURCE_UNKNOWN
) -> MappingScreen | None:
    profile = profile_for(source, file_type)
    overrides = profile.aliases if profile is not None else None
    read_keys: Callable[[Path], FileSummary]
    suggest: Callable[[list[str]], FieldMapping]
    parse_record: Callable[[list[tuple[str, str]], FieldMapping], ParsedRow]
    if file_type == _TYPE_CSV:
        read_keys, noun = read_csv_headers, "columns"
        suggest = partial(
            suggest_mapping,
            alias_overrides=overrides,
            ignored_keys=profile.ignored_keys if profile is not None else frozenset(),
        )
        parse_record = _parse_csv_lines
    elif file_type == _TYPE_RIS:
        read_keys, noun = read_ris_tags, "tags"
        suggest = partial(suggest_ris_mapping, alias_overrides=overrides)
        parse_record = parse_ris_record
    elif file_type == _TYPE_NBIB:
        read_keys, noun = read_nbib_tags, "tags"
        suggest = partial(suggest_nbib_mapping, alias_overrides=overrides)
        parse_record = parse_nbib_record
    elif file_type == _TYPE_BIBTEX:
        read_keys, noun = read_bibtex_fields, "fields"
        suggest = partial(suggest_bibtex_mapping, alias_overrides=overrides)
        parse_record = parse_bibtex_record
    else:
        return None

    try:
        summary = read_keys(path)
    except ValueError as exc:
        with container:
            ui.notify(str(exc), type="negative")
        return None

    if not summary.samples:
        with container:
            ui.notify(f"{path.name} has no {noun} to map", type="negative")
        return None

    suggestion = suggest(list(summary.samples))
    if profile is not None and profile.list_delimiter is not None:
        suggestion = replace(suggestion, list_delimiter=profile.list_delimiter)

    def preview(mapping: FieldMapping) -> Record:
        row = parse_record(list(summary.samples.items()), mapping)
        if profile is None:
            return row.record
        return profile.fix_record(row.raw_fields, row.record)

    return render_mapping_table(
        container,
        summary,
        suggestion,
        show_delimiter=file_type in (_TYPE_CSV, _TYPE_BIBTEX),
        preview=preview,
    )


def _store(
    session: Session, path: Path, file_type: str, result: ParseResult, source: str
) -> SourceFile:
    result = apply_profile(result, profile_for(source, file_type))
    source_file = store_parsed_rows(
        session,
        filename=path.name,
        path=str(path),
        format=file_type,
        source=source if source != _SOURCE_UNKNOWN else None,
        parsed_rows=[(row.record, row.raw_fields) for row in result.rows],
        skipped_rows=[(row.row_number, row.reason) for row in result.skipped],
    )
    log_import(session, source_file)
    return source_file


def import_csv(
    session: Session, path: Path, mapping: FieldMapping, source: str = _SOURCE_UNKNOWN
) -> SourceFile:
    return _store(session, path, _TYPE_CSV, parse_csv_file(path, mapping), source)


def import_ris(
    session: Session, path: Path, mapping: FieldMapping, source: str = _SOURCE_UNKNOWN
) -> SourceFile:
    return _store(session, path, _TYPE_RIS, parse_ris_file(path, mapping), source)


def import_nbib(
    session: Session, path: Path, mapping: FieldMapping, source: str = _SOURCE_UNKNOWN
) -> SourceFile:
    return _store(session, path, _TYPE_NBIB, parse_nbib_file(path, mapping), source)


def import_bibtex(
    session: Session, path: Path, mapping: FieldMapping, source: str = _SOURCE_UNKNOWN
) -> SourceFile:
    return _store(session, path, _TYPE_BIBTEX, parse_bibtex_file(path, mapping), source)


def import_file(
    session: Session,
    path: Path,
    file_type: str,
    mapping: FieldMapping,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    if file_type == _TYPE_CSV:
        return import_csv(session, path, mapping, source)
    if file_type == _TYPE_RIS:
        return import_ris(session, path, mapping, source)
    if file_type == _TYPE_NBIB:
        return import_nbib(session, path, mapping, source)
    if file_type == _TYPE_BIBTEX:
        return import_bibtex(session, path, mapping, source)
    raise ValueError(f"unsupported file type: {file_type!r}")


@dataclass
class ImportView:
    middle: Element
    on_import: Callable[[Path, str, FieldMapping, str], None]
    path: Path | None = None
    file_type: str = _TYPE_UNKNOWN
    source: str = _SOURCE_UNKNOWN
    mapping_screen: MappingScreen | None = None
    import_button: ui.button | None = None

    async def _select_file(self) -> None:
        picked = await pick_file()
        if picked is not None:
            self.path = picked
            self.file_type = detect_type(picked) or _TYPE_UNKNOWN
            self.source = _SOURCE_UNKNOWN
            if self.file_type != _TYPE_UNKNOWN:
                self.source = detect_source(picked, self.file_type) or _SOURCE_UNKNOWN
            self.render()

    def _set_type(self, file_type: str) -> None:
        self.file_type = file_type
        self.render()

    def _set_source(self, source: str) -> None:
        self.source = source
        self.render()

    def _import(self) -> None:
        assert self.path is not None
        assert self.mapping_screen is not None
        self.on_import(
            self.path,
            self.file_type,
            self.mapping_screen.current_mapping(),
            self.source,
        )

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
                    # Mirrors the warning icon's slot so the dropdowns stay centred.
                    ui.icon("warning", size="sm").classes("invisible")
                    source_select = (
                        ui.select(_SOURCE_OPTIONS, value=self.source, label="Source")
                        .props("dense outlined")
                        .classes("w-48")
                    )
                    source_select.on_value_change(lambda e: self._set_source(e.value))

                    type_select = (
                        ui.select(_TYPE_OPTIONS, value=self.file_type, label="Type")
                        .props("dense outlined")
                        .classes("w-48")
                    )
                    type_select.on_value_change(lambda e: self._set_type(e.value))

                    notice = ui.icon("warning", size="sm").classes("text-orange-7")
                    if (
                        self.source != _SOURCE_UNKNOWN
                        and type_known
                        and profile_for(self.source, self.file_type) is None
                    ):
                        notice.tooltip(
                            "No profile for this source/type combination"
                            " — using the default parser."
                        )
                    else:
                        notice.classes("invisible")

                mapping_container = ui.column().classes("items-center w-full")
                if self.path is not None:
                    self.mapping_screen = render_mapping(
                        mapping_container, self.file_type, self.path, self.source
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


def render_import_view(
    middle: Element, on_import: Callable[[Path, str, FieldMapping, str], None]
) -> ImportView:
    view = ImportView(middle=middle, on_import=on_import)
    view.render()
    return view
