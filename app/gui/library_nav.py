from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from functools import partial

from nicegui import ui
from nicegui.element import Element

from app.db.models import SourceFile

_SELECTED_CLASS = "bg-blue-100"
_IMPORT_KEY = "import"
_OVERVIEW_KEY = "library:overview"
_TABLE_KEY = "library:table"
_HEADING_CLASSES = "w-44 text-xs text-grey-6 pt-1 text-center"


@dataclass
class LeftPanelNav:
    middle: Element
    buttons: dict[str, ui.button] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    views: dict[str, Callable[[], Awaitable[None] | None]] = field(default_factory=dict)
    selected_key: str | None = None

    def show_placeholder(self, label: str) -> None:
        self.middle.clear()
        with self.middle:
            ui.label(label)

    def clear_selection(self) -> None:
        if self.selected_key is not None:
            self.buttons[self.selected_key].classes(remove=_SELECTED_CLASS)
        self.selected_key = None

    def highlight(self, key: str) -> None:
        self.clear_selection()
        self.buttons[key].classes(add=_SELECTED_CLASS)
        self.selected_key = key

    def select(self, key: str) -> Awaitable[None] | None:
        self.highlight(key)
        view = self.views.get(key)
        if view is not None:
            return view()
        self.show_placeholder(self.labels[key])
        return None


def render_left_panel(
    left: Element,
    middle: Element,
    source_files: Sequence[SourceFile],
    on_import: Callable[[], Awaitable[None] | None] | None = None,
    on_overview: Callable[[], Awaitable[None] | None] | None = None,
    on_overview_settings: Callable[[], Awaitable[None] | None] | None = None,
    on_table: Callable[[], Awaitable[None] | None] | None = None,
    on_table_settings: Callable[[], Awaitable[None] | None] | None = None,
    on_source_file: Callable[[int], Awaitable[None] | None] | None = None,
) -> LeftPanelNav:
    nav = LeftPanelNav(middle=middle)
    ui.add_css(
        ".source-file-btn .q-btn__content"
        " { white-space: normal; overflow-wrap: anywhere; text-align: center; }"
    )

    def handle_import() -> Awaitable[None] | None:
        nav.select(_IMPORT_KEY)
        return on_import() if on_import is not None else None

    def handle_overview_settings() -> Awaitable[None] | None:
        nav.highlight(_OVERVIEW_KEY)
        return on_overview_settings() if on_overview_settings is not None else None

    def handle_table_settings() -> Awaitable[None] | None:
        nav.highlight(_TABLE_KEY)
        return on_table_settings() if on_table_settings is not None else None

    if on_overview is not None:
        nav.views[_OVERVIEW_KEY] = on_overview
    if on_table is not None:
        nav.views[_TABLE_KEY] = on_table

    left.clear()
    with left:
        import_button = (
            ui.button("Import", color=None, on_click=handle_import)
            .classes("w-44 text-sm")
            .props("dense")
        )
        nav.buttons[_IMPORT_KEY] = import_button
        nav.labels[_IMPORT_KEY] = "Import"
        ui.separator()

        ui.label("Library").classes(_HEADING_CLASSES)
        with ui.row().classes("w-44 items-center gap-1 no-wrap"):
            overview_button = (
                ui.button("Overview", color=None)
                .classes("flex-grow text-sm")
                .props("dense")
            )
            ui.button(
                icon="settings", color=None, on_click=handle_overview_settings
            ).props("flat dense round size=sm")
        overview_button.on_click(lambda: nav.select(_OVERVIEW_KEY))
        nav.buttons[_OVERVIEW_KEY] = overview_button
        nav.labels[_OVERVIEW_KEY] = "Overview"

        with ui.row().classes("w-44 items-center gap-1 no-wrap"):
            table_button = (
                ui.button("Table", color=None)
                .classes("flex-grow text-sm")
                .props("dense")
            )
            ui.button(
                icon="settings", color=None, on_click=handle_table_settings
            ).props("flat dense round size=sm")
        table_button.on_click(lambda: nav.select(_TABLE_KEY))
        nav.buttons[_TABLE_KEY] = table_button
        nav.labels[_TABLE_KEY] = "Table"

        if source_files:
            ui.separator()
            ui.label("Imported files").classes(_HEADING_CLASSES)

        for source_file in source_files:
            key = f"source_file:{source_file.id}"
            button = (
                ui.button(source_file.filename, color=None)
                .classes("w-44 text-xs source-file-btn")
                .props("dense")
            )
            button.on_click(lambda key=key: nav.select(key))
            nav.buttons[key] = button
            nav.labels[key] = source_file.filename
            if on_source_file is not None:
                nav.views[key] = partial(on_source_file, source_file.id)

    return nav
