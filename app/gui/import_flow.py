from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from pathlib import Path

from nicegui import app, ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.db.store import store_parsed_rows
from app.gui.activity_log import log_import
from app.gui.busy import run_busy
from app.gui.mapping_table import MappingScreen, render_mapping_table
from app.models.record import Record
from app.parsers.bibtex import (
    parse_bibtex_file,
    parse_bibtex_record,
    read_bibtex_fields,
    suggest_bibtex_mapping,
)
from app.parsers.common import FileSummary, ParsedRow, ParseResult, merge_summaries
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
from app.parsers.profiles.base import FormatProfile
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
_TYPE_TSV = "tsv"
_TYPE_BIBTEX = "bibtex"
_TYPE_OPTIONS = {
    _TYPE_UNKNOWN: "Unknown",
    _TYPE_RIS: "RIS",
    _TYPE_NBIB: "NBIB",
    _TYPE_CSV: "CSV",
    _TYPE_TSV: "TSV",
    _TYPE_BIBTEX: "BibTeX",
}
_TSV_DELIMITER = "\t"

_SOURCE_UNKNOWN = "unknown"
_SOURCE_OPTIONS = {
    _SOURCE_UNKNOWN: "Unknown",
    **{key: profile.label for key, profile in PROFILES.items()},
}

_MIXED_WARNING = (
    "The selected files look like they come from different sources or types."
    " Make sure you are importing files from the same source and of the same type."
)


async def pick_files() -> list[Path]:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(allow_multiple=True)
    return [Path(path) for path in selected] if selected else []


def _parse_csv_lines(lines: list[tuple[str, str]], mapping: FieldMapping) -> ParsedRow:
    return parse_csv_record(dict(lines), mapping)


@dataclass
class _FormatHandlers:
    read_keys: Callable[[Path], FileSummary]
    suggest: Callable[[list[str]], FieldMapping]
    parse_record: Callable[[list[tuple[str, str]], FieldMapping], ParsedRow]
    noun: str
    profile: FormatProfile | None


def _handlers(file_type: str, source: str) -> _FormatHandlers | None:
    profile = profile_for(source, file_type)
    overrides = profile.aliases if profile is not None else None
    if file_type in (_TYPE_CSV, _TYPE_TSV):
        suggest = partial(
            suggest_mapping,
            alias_overrides=overrides,
            ignored_keys=profile.ignored_keys if profile is not None else frozenset(),
        )
        read_keys = (
            read_csv_headers
            if file_type == _TYPE_CSV
            else partial(read_csv_headers, delimiter=_TSV_DELIMITER)
        )
        return _FormatHandlers(read_keys, suggest, _parse_csv_lines, "columns", profile)
    if file_type == _TYPE_RIS:
        suggest = partial(suggest_ris_mapping, alias_overrides=overrides)
        return _FormatHandlers(
            read_ris_tags, suggest, parse_ris_record, "tags", profile
        )
    if file_type == _TYPE_NBIB:
        suggest = partial(suggest_nbib_mapping, alias_overrides=overrides)
        return _FormatHandlers(
            read_nbib_tags, suggest, parse_nbib_record, "tags", profile
        )
    if file_type == _TYPE_BIBTEX:
        suggest = partial(suggest_bibtex_mapping, alias_overrides=overrides)
        return _FormatHandlers(
            read_bibtex_fields, suggest, parse_bibtex_record, "fields", profile
        )
    return None


def _suggestion(handlers: _FormatHandlers, summary: FileSummary) -> FieldMapping:
    suggestion = handlers.suggest(list(summary.samples))
    profile = handlers.profile
    if profile is not None and profile.list_delimiter is not None:
        suggestion = replace(suggestion, list_delimiter=profile.list_delimiter)
    return suggestion


def _preview(
    handlers: _FormatHandlers, summary: FileSummary
) -> Callable[[FieldMapping], Record]:
    def preview(mapping: FieldMapping) -> Record:
        row = handlers.parse_record(list(summary.samples.items()), mapping)
        if handlers.profile is None:
            return row.record
        return handlers.profile.fix_record(row.raw_fields, row.record)

    return preview


def preview_for(
    file_type: str, source: str, summary: FileSummary
) -> Callable[[FieldMapping], Record]:
    handlers = _handlers(file_type, source)
    if handlers is None:
        raise ValueError(f"unsupported file type: {file_type!r}")
    return _preview(handlers, summary)


def shows_delimiter(file_type: str) -> bool:
    return file_type in (_TYPE_CSV, _TYPE_TSV, _TYPE_BIBTEX)


def _detect(path: Path) -> tuple[str, str]:
    file_type = detect_type(path) or _TYPE_UNKNOWN
    if file_type == _TYPE_UNKNOWN:
        return file_type, _SOURCE_UNKNOWN
    return file_type, detect_source(path, file_type) or _SOURCE_UNKNOWN


def common_detection(detected: list[tuple[str, str]]) -> tuple[str, str]:
    types = {file_type for file_type, _ in detected}
    sources = {source for _, source in detected}
    file_type = types.pop() if len(types) == 1 else _TYPE_UNKNOWN
    source = sources.pop() if len(sources) == 1 else _SOURCE_UNKNOWN
    return file_type, source


def read_summary(file_type: str, path: Path) -> FileSummary | None:
    handlers = _handlers(file_type, _SOURCE_UNKNOWN)
    return handlers.read_keys(path) if handlers is not None else None


def render_mapping(
    container: Element,
    file_type: str,
    name: str,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> MappingScreen | None:
    handlers = _handlers(file_type, source)
    if handlers is None:
        return None

    if not summary.samples:
        with container:
            ui.notify(f"No {handlers.noun} to map in {name}", type="negative")
        return None

    return render_mapping_table(
        container,
        summary,
        _suggestion(handlers, summary),
        show_delimiter=shows_delimiter(file_type),
        preview=_preview(handlers, summary),
    )


def _store(
    session: Session,
    path: Path,
    file_type: str,
    mapping: FieldMapping,
    summary: FileSummary,
    result: ParseResult,
    source: str,
) -> SourceFile:
    handlers = _handlers(file_type, source)
    assert handlers is not None
    result = apply_profile(result, handlers.profile)
    source_file = store_parsed_rows(
        session,
        filename=path.name,
        path=str(path),
        format=file_type,
        source=source if source != _SOURCE_UNKNOWN else None,
        parsed_rows=[(row.record, row.raw_fields) for row in result.rows],
        skipped_rows=[(row.row_number, row.reason) for row in result.skipped],
    )
    source_file.field_mapping = asdict(mapping)
    source_file.suggested_mapping = asdict(_suggestion(handlers, summary))
    source_file.file_summary = asdict(summary)
    log_import(session, source_file)
    return source_file


def import_csv(
    session: Session,
    path: Path,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    result = parse_csv_file(path, mapping)
    return _store(session, path, _TYPE_CSV, mapping, summary, result, source)


def import_tsv(
    session: Session,
    path: Path,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    result = parse_csv_file(path, mapping, delimiter=_TSV_DELIMITER)
    return _store(session, path, _TYPE_TSV, mapping, summary, result, source)


def import_ris(
    session: Session,
    path: Path,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    result = parse_ris_file(path, mapping)
    return _store(session, path, _TYPE_RIS, mapping, summary, result, source)


def import_nbib(
    session: Session,
    path: Path,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    result = parse_nbib_file(path, mapping)
    return _store(session, path, _TYPE_NBIB, mapping, summary, result, source)


def import_bibtex(
    session: Session,
    path: Path,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    result = parse_bibtex_file(path, mapping)
    return _store(session, path, _TYPE_BIBTEX, mapping, summary, result, source)


def import_file(
    session: Session,
    path: Path,
    file_type: str,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = _SOURCE_UNKNOWN,
) -> SourceFile:
    if file_type == _TYPE_CSV:
        return import_csv(session, path, mapping, summary, source)
    if file_type == _TYPE_TSV:
        return import_tsv(session, path, mapping, summary, source)
    if file_type == _TYPE_RIS:
        return import_ris(session, path, mapping, summary, source)
    if file_type == _TYPE_NBIB:
        return import_nbib(session, path, mapping, summary, source)
    if file_type == _TYPE_BIBTEX:
        return import_bibtex(session, path, mapping, summary, source)
    raise ValueError(f"unsupported file type: {file_type!r}")


OnImport = Callable[
    [list[tuple[Path, FileSummary]], str, FieldMapping, str], Awaitable[None] | None
]


@dataclass
class ImportView:
    middle: Element
    on_import: OnImport
    paths: list[Path] = field(default_factory=list)
    detected: list[tuple[str, str]] = field(default_factory=list)
    file_type: str = _TYPE_UNKNOWN
    source: str = _SOURCE_UNKNOWN
    summaries: list[FileSummary] = field(default_factory=list)
    mapping_screen: MappingScreen | None = None
    import_button: ui.button | None = None

    def _name(self) -> str:
        if len(self.paths) == 1:
            return self.paths[0].name
        return f"{len(self.paths)} files"

    def _mixed(self) -> bool:
        return len(set(self.detected)) > 1

    def _mixed_details(self) -> str:
        return "; ".join(
            f"{path.name}: {_TYPE_OPTIONS[file_type]}, {_SOURCE_OPTIONS[source]}"
            for path, (file_type, source) in zip(self.paths, self.detected, strict=True)
        )

    async def _select_files(self) -> None:
        picked = await pick_files()
        if picked:
            self.paths = picked
            self.detected = await run_busy(
                f"Reading {self._name()}…", lambda: [_detect(path) for path in picked]
            )
            self.file_type, self.source = common_detection(self.detected)
            if self._mixed():
                with self.middle:
                    ui.notify(_MIXED_WARNING, type="warning")
            await self._read_files()

    async def _set_type(self, file_type: str) -> None:
        self.file_type = file_type
        await self._read_files()

    async def _read_files(self) -> None:
        self.summaries = []
        paths = self.paths
        file_type = self.file_type

        def read() -> list[FileSummary]:
            summaries = [read_summary(file_type, path) for path in paths]
            return [summary for summary in summaries if summary is not None]

        if paths:
            try:
                self.summaries = await run_busy(f"Reading {self._name()}…", read)
            except ValueError as exc:
                with self.middle:
                    ui.notify(str(exc), type="negative")
        self.render()

    def _set_source(self, source: str) -> None:
        self.source = source
        self.render()

    def _import(self) -> Awaitable[None] | None:
        assert self.paths
        assert self.mapping_screen is not None
        return self.on_import(
            list(zip(self.paths, self.summaries, strict=True)),
            self.file_type,
            self.mapping_screen.current_mapping(),
            self.source,
        )

    def render(self) -> None:
        type_known = self.file_type != _TYPE_UNKNOWN
        has_file = bool(self.paths)

        self.middle.clear()
        with self.middle:
            with ui.column().classes("gap-4 pt-4 items-center w-full"):
                with ui.row().classes("items-center gap-2"):
                    if len(self.paths) > 1:
                        files_label = ui.label(f"{len(self.paths)} files selected")
                        files_label.tooltip(", ".join(path.name for path in self.paths))
                    else:
                        files_label = ui.label(
                            self.paths[0].name if self.paths else "No file selected"
                        )
                    files_label.classes("text-sm")
                    if self._mixed():
                        ui.icon("warning", size="sm").classes("text-orange-7").tooltip(
                            f"{_MIXED_WARNING} Detected: {self._mixed_details()}"
                        )
                    ui.button("Select files", on_click=self._select_files).props(
                        "dense"
                    )

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
                if self.paths and self.summaries:
                    self.mapping_screen = render_mapping(
                        mapping_container,
                        self.file_type,
                        self._name(),
                        merge_summaries(self.summaries),
                        self.source,
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


def render_import_view(middle: Element, on_import: OnImport) -> ImportView:
    view = ImportView(middle=middle, on_import=on_import)
    view.render()
    return view
