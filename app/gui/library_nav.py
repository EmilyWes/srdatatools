from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from functools import partial

from nicegui import ui
from nicegui.element import Element

from app.db.models import SourceFile

_SELECTED_CLASS = "bg-secondary"
_IMPORT_KEY = "import"
_DASHBOARD_KEY = "library:dashboard"
_TABLE_KEY = "library:table"
_ABOUT_KEY = "about"
_HELP_KEY = "help"
_HEADING_CLASSES = "label-medium px-4 pt-3 pb-1"
_FILE_LIST_CLASSES = "w-full gap-1 flex-grow min-h-0 overflow-y-auto no-wrap"
_ITEM_PROPS = "flat no-caps align=left"
_ITEM_CLASSES = "nav-item w-full"
_GEAR_PROPS = "flat dense round size=sm"


@dataclass
class LeftPanelNav:
    buttons: dict[str, ui.button] = field(default_factory=dict)
    views: dict[str, Callable[[], Awaitable[None] | None]] = field(default_factory=dict)
    selected_key: str | None = None

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
        return view() if view is not None else None


def render_left_panel(
    left: Element,
    source_files: Sequence[SourceFile],
    on_import: Callable[[], Awaitable[None] | None] | None = None,
    on_dashboard: Callable[[], Awaitable[None] | None] | None = None,
    on_dashboard_settings: Callable[[], Awaitable[None] | None] | None = None,
    on_table: Callable[[], Awaitable[None] | None] | None = None,
    on_table_settings: Callable[[], Awaitable[None] | None] | None = None,
    on_source_file: Callable[[int], Awaitable[None] | None] | None = None,
    on_about: Callable[[], Awaitable[None] | None] | None = None,
    on_help: Callable[[], Awaitable[None] | None] | None = None,
) -> LeftPanelNav:
    nav = LeftPanelNav()
    ui.add_css(
        ".source-file-btn { height: auto; min-height: 40px; padding: 6px 12px; }"
        " .source-file-btn .q-btn__content { gap: 8px; flex-wrap: nowrap; }"
        " .source-file-btn .block { white-space: normal; overflow-wrap: anywhere;"
        " text-align: left; font-size: 13px; line-height: 1.3; }"
    )

    def handle_import() -> Awaitable[None] | None:
        nav.highlight(_IMPORT_KEY)
        return on_import() if on_import is not None else None

    def handle_dashboard_settings() -> Awaitable[None] | None:
        nav.highlight(_DASHBOARD_KEY)
        return on_dashboard_settings() if on_dashboard_settings is not None else None

    def handle_table_settings() -> Awaitable[None] | None:
        nav.highlight(_TABLE_KEY)
        return on_table_settings() if on_table_settings is not None else None

    if on_dashboard is not None:
        nav.views[_DASHBOARD_KEY] = on_dashboard
    if on_table is not None:
        nav.views[_TABLE_KEY] = on_table
    if on_about is not None:
        nav.views[_ABOUT_KEY] = on_about
    if on_help is not None:
        nav.views[_HELP_KEY] = on_help

    left.clear()
    with left:
        import_button = (
            ui.button("Import", icon="upload_file", on_click=handle_import)
            .classes("fab w-full my-2")
            .props("unelevated no-caps")
        )
        nav.buttons[_IMPORT_KEY] = import_button
        ui.separator().classes("my-1")

        ui.label("Library").classes(_HEADING_CLASSES)
        with ui.row().classes("w-full items-center gap-1 no-wrap"):
            dashboard_button = (
                ui.button("Dashboard", icon="insights", color=None)
                .classes(f"{_ITEM_CLASSES} flex-grow")
                .props(_ITEM_PROPS)
            )
            ui.button(
                icon="settings", color=None, on_click=handle_dashboard_settings
            ).props(_GEAR_PROPS).classes("text-on-surface-variant")
        dashboard_button.on_click(lambda: nav.select(_DASHBOARD_KEY))
        nav.buttons[_DASHBOARD_KEY] = dashboard_button

        with ui.row().classes("w-full items-center gap-1 no-wrap"):
            table_button = (
                ui.button("Table", icon="table_chart", color=None)
                .classes(f"{_ITEM_CLASSES} flex-grow")
                .props(_ITEM_PROPS)
            )
            ui.button(
                icon="settings", color=None, on_click=handle_table_settings
            ).props(_GEAR_PROPS).classes("text-on-surface-variant")
        table_button.on_click(lambda: nav.select(_TABLE_KEY))
        nav.buttons[_TABLE_KEY] = table_button

        if source_files:
            ui.separator().classes("my-1")
            ui.label("Imported files").classes(_HEADING_CLASSES)

        # Fills the space above About/Help and scrolls when the files don't fit.
        with ui.column().classes(_FILE_LIST_CLASSES):
            for source_file in source_files:
                key = f"source_file:{source_file.id}"
                button = (
                    ui.button(source_file.filename, icon="description", color=None)
                    .classes(f"{_ITEM_CLASSES} source-file-btn")
                    .props(_ITEM_PROPS)
                )
                button.on_click(lambda key=key: nav.select(key))
                nav.buttons[key] = button
                if on_source_file is not None:
                    nav.views[key] = partial(on_source_file, source_file.id)

        with ui.column().classes("w-full gap-1 pt-2 pb-4"):
            for key, text, icon in (
                (_ABOUT_KEY, "About", "info"),
                (_HELP_KEY, "Help", "help_outline"),
            ):
                button = (
                    ui.button(text, icon=icon, color=None)
                    .classes(_ITEM_CLASSES)
                    .props(_ITEM_PROPS)
                )
                button.on_click(lambda key=key: nav.select(key))
                nav.buttons[key] = button

    return nav
