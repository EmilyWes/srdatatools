from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nicegui import app, ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.activity_log import log_import
from app.db.models import SourceFile
from app.db.store import store_parsed_rows
from app.gui.busy import run_busy
from app.gui.mapping_table import ROW_FIELD_CSS, MappingScreen, render_mapping_table
from app.gui.quirks_overview import (
    VIEW_MAPPING,
    VIEW_PARSING,
    MappingParsingViews,
    QuirksScreen,
    render_quirks_overview,
    render_view_toggle,
)
from app.parsers.bibtex import (
    parse_bibtex_file,
    read_bibtex_fields,
    suggest_bibtex_mapping,
)
from app.parsers.common import (
    UNKNOWN,
    FileSummary,
    FileType,
    ParseResult,
    is_file_type,
    merge_summaries,
)
from app.parsers.csv_ import (
    parse_csv_file,
    read_csv_headers,
    suggest_mapping,
)
from app.parsers.detect import detect_source, detect_type
from app.parsers.excel import (
    parse_excel_file,
    read_excel_headers,
    read_excel_sheets,
)
from app.parsers.mapping import FieldMapping
from app.parsers.nbib import (
    parse_nbib_file,
    read_nbib_tags,
    suggest_nbib_mapping,
)
from app.parsers.profiles import (
    PROFILES,
    FormatProfile,
    has_profile,
)
from app.parsers.profiles.overview import (
    ParsingChoices,
    default_choices,
    dump_choices,
    profile_with,
    quirk_boxes,
)
from app.parsers.quirks import ParseSettings
from app.parsers.ris import (
    parse_ris_file,
    read_ris_tags,
    suggest_ris_mapping,
)

_TYPE_OPTIONS = {
    UNKNOWN: "Unknown",
    "ris": "RIS",
    "nbib": "NBIB",
    "csv": "CSV",
    "tsv": "TSV",
    "excel": "Excel",
    "bibtex": "BibTeX",
}
_TSV_DELIMITER = "\t"

_SOURCE_OPTIONS = {
    UNKNOWN: "Unknown",
    **{key: profile.label for key, profile in PROFILES.items()},
}

_MIXED_WARNING = (
    "The selected files look like they come from different sources or types."
    " Make sure you are importing files from the same source and of the same type."
)
_EXCEL_SINGLE_FILE = "Excel import takes one file at a time"

# The second column is fixed to the dropdown width (w-32) so a long file name
# overflows to the right instead of moving the button and dropdowns.
GRID_COLUMNS = "max-content 8rem"
GRID_CLASSES = "items-center justify-items-start gap-x-1 gap-y-2"
CELL_ROW_CLASSES = "items-center gap-2 no-wrap"
FILE_LABEL_CLASSES = "text-sm whitespace-nowrap"
SELECT_PROPS = "dense outlined options-dense popup-content-class=text-xs"
BUTTON_PROPS = "dense size=11px"
SELECT_CLASSES = "mapping-field text-xs w-32"


async def pick_files() -> list[Path]:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(allow_multiple=True)
    return [Path(path) for path in selected] if selected else []


@dataclass(frozen=True)
class _TypeHandlers:
    """One Type's parser functions, called the same way for every Type."""

    read_keys: Callable[[Path, str | None, ParseSettings], FileSummary]
    suggest: Callable[[list[str], FormatProfile], FieldMapping]
    parse_file: Callable[[Path, FieldMapping, str | None, ParseSettings], ParseResult]
    noun: str


def _suggest_columns(keys: list[str], profile: FormatProfile) -> FieldMapping:
    return suggest_mapping(keys, profile.suggestions, profile.ignored_keys)


def _delimited(delimiter: str | None) -> _TypeHandlers:
    return _TypeHandlers(
        read_keys=lambda path, _, settings: read_csv_headers(path, delimiter, settings),
        suggest=_suggest_columns,
        parse_file=lambda path, mapping, _, settings: parse_csv_file(
            path, mapping, delimiter, settings
        ),
        noun="columns",
    )


_TYPES: dict[FileType, _TypeHandlers] = {
    "csv": _delimited(None),
    "tsv": _delimited(_TSV_DELIMITER),
    "excel": _TypeHandlers(
        read_keys=lambda path, sheet, _: read_excel_headers(path, sheet),
        suggest=_suggest_columns,
        parse_file=parse_excel_file,
        noun="columns",
    ),
    "ris": _TypeHandlers(
        read_keys=lambda path, _, __: read_ris_tags(path),
        suggest=lambda keys, profile: suggest_ris_mapping(keys, profile.suggestions),
        parse_file=lambda path, mapping, _, settings: parse_ris_file(
            path, mapping, settings
        ),
        noun="tags",
    ),
    "nbib": _TypeHandlers(
        read_keys=lambda path, _, __: read_nbib_tags(path),
        suggest=lambda keys, profile: suggest_nbib_mapping(keys, profile.suggestions),
        parse_file=lambda path, mapping, _, settings: parse_nbib_file(
            path, mapping, settings
        ),
        noun="tags",
    ),
    "bibtex": _TypeHandlers(
        read_keys=lambda path, _, __: read_bibtex_fields(path),
        suggest=lambda keys, profile: suggest_bibtex_mapping(keys, profile.suggestions),
        parse_file=lambda path, mapping, _, settings: parse_bibtex_file(
            path, mapping, settings
        ),
        noun="fields",
    ),
}


def _suggestion(file_type: FileType, source: str, summary: FileSummary) -> FieldMapping:
    return _TYPES[file_type].suggest(
        list(summary.samples), profile_with(file_type, source)
    )


def type_label(file_type: str) -> str:
    return _TYPE_OPTIONS[file_type]


def _detect(path: Path) -> tuple[str, str]:
    file_type = detect_type(path)
    if file_type is None:
        return UNKNOWN, UNKNOWN
    return file_type, detect_source(path, file_type) or UNKNOWN


def common_detection(detected: list[tuple[str, str]]) -> tuple[str, str]:
    types = {file_type for file_type, _ in detected}
    sources = {source for _, source in detected}
    file_type = types.pop() if len(types) == 1 else UNKNOWN
    source = sources.pop() if len(sources) == 1 else UNKNOWN
    return file_type, source


def read_summary(
    file_type: FileType, path: Path, sheet: str | None = None
) -> FileSummary:
    settings = profile_with(file_type, UNKNOWN).settings
    return _TYPES[file_type].read_keys(path, sheet, settings)


def render_mapping(
    container: Element,
    file_type: FileType,
    name: str,
    summary: FileSummary,
    source: str = UNKNOWN,
) -> MappingScreen | None:
    if not summary.samples:
        with container:
            ui.notify(f"No {_TYPES[file_type].noun} to map in {name}", type="negative")
        return None

    return render_mapping_table(
        container, summary, _suggestion(file_type, source, summary)
    )


def import_file(
    session: Session,
    path: Path,
    file_type: FileType,
    mapping: FieldMapping,
    summary: FileSummary,
    source: str = UNKNOWN,
    sheet: str | None = None,
    choices: ParsingChoices | None = None,
) -> SourceFile:
    profile = profile_with(file_type, source, choices)
    result = _TYPES[file_type].parse_file(path, mapping, sheet, profile.settings)
    source_file = store_parsed_rows(
        session,
        filename=path.name,
        path=str(path),
        format=file_type,
        source=source if source != UNKNOWN else None,
        sheet=sheet,
        parsed_rows=[(row.record, row.raw_fields) for row in result.rows],
        skipped_rows=[(row.row_number, row.reason) for row in result.skipped],
    )
    source_file.field_mapping = mapping.model_dump()
    source_file.suggested_mapping = _suggestion(file_type, source, summary).model_dump()
    source_file.file_summary = asdict(summary)
    source_file.quirk_choices = dump_choices(
        choices or default_choices(file_type, source)
    )
    log_import(session, source_file)
    return source_file


OnImport = Callable[
    [
        list[tuple[Path, FileSummary]],
        FileType,
        FieldMapping,
        str,
        str | None,
        ParsingChoices,
        bool,
    ],
    Awaitable[None] | None,
]


@dataclass
class ImportView:
    middle: Element
    on_import: OnImport
    paths: list[Path] = field(default_factory=list)
    detected: list[tuple[str, str]] = field(default_factory=list)
    file_type: str = UNKNOWN
    source: str = UNKNOWN
    summaries: list[FileSummary] = field(default_factory=list)
    sheets: list[str] = field(default_factory=list)
    sheet: str | None = None
    view: str | None = VIEW_MAPPING
    mapping_screen: MappingScreen | None = None
    quirks_screen: QuirksScreen[ParsingChoices] | None = None
    views: MappingParsingViews | None = None
    import_button: ui.button | None = None
    import_clean_button: ui.button | None = None

    def _name(self) -> str:
        if len(self.paths) == 1:
            return self.paths[0].name
        return f"{len(self.paths)} files"

    def _too_many_for_excel(self) -> bool:
        return self.file_type == "excel" and len(self.paths) > 1

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
            self.sheet = None
            self.detected = await run_busy(
                f"Reading {self._name()}…", lambda: [_detect(path) for path in picked]
            )
            self.file_type, self.source = common_detection(self.detected)
            detected = UNKNOWN not in (self.file_type, self.source)
            self.view = None if detected else VIEW_MAPPING
            if self._mixed():
                with self.middle:
                    ui.notify(_MIXED_WARNING, type="warning")
            await self._read_files()

    async def _set_type(self, file_type: str) -> None:
        self.file_type = file_type
        await self._read_files()

    async def _set_sheet(self, sheet: str) -> None:
        self.sheet = sheet
        await self._read_files()

    async def _read_files(self) -> None:
        self.summaries = []
        self.sheets = []
        paths = self.paths
        file_type = self.file_type
        previous_sheet = self.sheet
        self.sheet = None

        def read() -> tuple[list[str], str | None, list[FileSummary]]:
            sheets = read_excel_sheets(paths[0]) if file_type == "excel" else []
            first_sheet = next(iter(sheets), None)
            sheet = previous_sheet if previous_sheet in sheets else first_sheet
            if not is_file_type(file_type):
                return sheets, sheet, []
            return sheets, sheet, [read_summary(file_type, p, sheet) for p in paths]

        if self._too_many_for_excel():
            with self.middle:
                ui.notify(_EXCEL_SINGLE_FILE, type="warning")
        elif paths:
            try:
                self.sheets, self.sheet, self.summaries = await run_busy(
                    f"Reading {self._name()}…", read
                )
            except ValueError as exc:
                with self.middle:
                    ui.notify(str(exc), type="negative")
        self.render()

    def _set_source(self, source: str) -> None:
        self.source = source
        self.render()

    def _import(self, clean: bool = False) -> Awaitable[None] | None:
        assert self.paths
        assert self.mapping_screen is not None
        assert self.quirks_screen is not None
        assert is_file_type(self.file_type)
        return self.on_import(
            list(zip(self.paths, self.summaries, strict=True)),
            self.file_type,
            self.mapping_screen.current_mapping(),
            self.source,
            self.sheet,
            self.quirks_screen.current_choices(),
            clean,
        )

    def _current_mapping(self) -> FieldMapping:
        # Parsing renders before the mapping table exists.
        if self.mapping_screen is None:
            return FieldMapping()
        return self.mapping_screen.current_mapping()

    def _on_view(self, view: str | None) -> None:
        """Parsing refreshes from the mapping's edits when it is shown."""
        self.view = view
        if view == VIEW_PARSING and self.quirks_screen is not None:
            self.quirks_screen.refresh_ordering()

    def _render_mapping_and_parsing(
        self, views: MappingParsingViews, file_type: FileType
    ) -> None:
        quirks_screen = render_quirks_overview(
            views.parsing,
            quirk_boxes(file_type, type_label(file_type)),
            default_choices(file_type, self.source),
            current_mapping=self._current_mapping,
        )
        mapping_screen = render_mapping(
            views.mapping,
            file_type,
            self._name(),
            merge_summaries(self.summaries),
            self.source,
        )
        if mapping_screen is None:
            views.parsing.clear()
            return
        self.mapping_screen, self.quirks_screen = mapping_screen, quirks_screen
        self.views = views
        self._on_view(self.view)

    def _no_mapping_reason(self, type_known: bool) -> str:
        if not self.paths:
            return "select a file first"
        if not type_known:
            return "please select the type"
        if self._too_many_for_excel():
            return _EXCEL_SINGLE_FILE
        return "file has no mapping available"

    def render(self) -> None:
        file_type = self.file_type if is_file_type(self.file_type) else None
        type_known = file_type is not None
        has_file = bool(self.paths)

        ui.add_css(ROW_FIELD_CSS)
        self.middle.clear()
        with self.middle:
            with ui.column().classes("gap-4 pt-4 items-center w-full"):
                with ui.grid(columns=GRID_COLUMNS).classes(GRID_CLASSES):
                    ui.button("Select files", on_click=self._select_files).props(
                        BUTTON_PROPS
                    )
                    with ui.row().classes(CELL_ROW_CLASSES):
                        if len(self.paths) > 1:
                            files_label = ui.label(f"{len(self.paths)} files selected")
                            files_label.tooltip(
                                ", ".join(path.name for path in self.paths)
                            )
                        else:
                            files_label = ui.label(
                                self.paths[0].name if self.paths else "No file selected"
                            )
                        files_label.classes(FILE_LABEL_CLASSES)
                        if self._mixed():
                            ui.icon("warning", size="sm").classes(
                                "text-orange-7"
                            ).tooltip(
                                f"{_MIXED_WARNING} Detected: {self._mixed_details()}"
                            )

                    ui.label("Select source:").classes("text-sm")
                    source_select = (
                        ui.select(_SOURCE_OPTIONS, value=self.source)
                        .props(SELECT_PROPS)
                        .classes(SELECT_CLASSES)
                    )
                    source_select.on_value_change(lambda e: self._set_source(e.value))

                    ui.label("Select type:").classes("text-sm")
                    with ui.row().classes(CELL_ROW_CLASSES):
                        type_select = (
                            ui.select(_TYPE_OPTIONS, value=self.file_type)
                            .props(SELECT_PROPS)
                            .classes(SELECT_CLASSES)
                        )
                        type_select.on_value_change(lambda e: self._set_type(e.value))
                        if (
                            self.source != UNKNOWN
                            and file_type is not None
                            and not has_profile(self.source, file_type)
                        ):
                            ui.icon("warning", size="sm").classes(
                                "text-orange-7"
                            ).tooltip(
                                "No profile for this source/type combination"
                                " — using the default parser."
                            )

                    if self.sheets:
                        ui.label("Select sheet:").classes("text-sm")
                        sheet_select = (
                            ui.select(self.sheets, value=self.sheet)
                            .props(SELECT_PROPS)
                            .classes(SELECT_CLASSES)
                        )
                        sheet_select.on_value_change(lambda e: self._set_sheet(e.value))

                self.mapping_screen = self.quirks_screen = None
                self.views = None
                can_render = bool(self.paths and self.summaries) and type_known
                has_samples = bool(merge_summaries(self.summaries).samples)
                views = render_view_toggle(
                    self.view if can_render and has_samples else None,
                    on_change=self._on_view,
                )
                if can_render:
                    assert file_type is not None
                    self._render_mapping_and_parsing(views, file_type)
                has_mapping = self.mapping_screen is not None
                if not has_mapping:
                    views.toggle.disable()
                    views.toggle.tooltip(self._no_mapping_reason(type_known))

                with ui.column().classes("items-center gap-2"):
                    self.import_button = ui.button(
                        "Import", icon="upload_file", on_click=lambda: self._import()
                    ).props("dense")
                    self.import_clean_button = ui.button(
                        "Import and clean",
                        icon="upload_file",
                        on_click=lambda: self._import(clean=True),
                    ).props("dense icon-right=cleaning_services")
                    for button in (self.import_button, self.import_clean_button):
                        button.classes("w-52 px-4").props("no-wrap")
                        button.set_enabled(has_file and type_known and has_mapping)
                        if not type_known:
                            button.tooltip("please select the type")
                        elif self._too_many_for_excel():
                            button.tooltip(_EXCEL_SINGLE_FILE)
                        elif not has_mapping:
                            button.tooltip("file has no mapping available")


def render_import_view(middle: Element, on_import: OnImport) -> ImportView:
    view = ImportView(middle=middle, on_import=on_import)
    view.render()
    return view
