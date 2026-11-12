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
_ABOUT_KEY = "about"
_HELP_KEY = "help"
_HEADING_CLASSES = "w-44 text-xs text-grey-6 pt-1 text-center"


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
    on_overview: Callable[[], Awaitable[None] | None] | None = None,
    on_overview_settings: Callable[[], Awaitable[None] | None] | None = None,
    on_table: Callable[[], Awaitable[None] | None] | None = None,
    on_table_settings: Callable[[], Awaitable[None] | None] | None = None,
    on_source_file: Callable[[int], Awaitable[None] | None] | None = None,
    on_about: Callable[[], Awaitable[None] | None] | None = None,
    on_help: Callable[[], Awaitable[None] | None] | None = None,
) -> LeftPanelNav:
    nav = LeftPanelNav()
    ui.add_css(
        ".source-file-btn .q-btn__content"
        " { white-space: normal; overflow-wrap: anywhere; text-align: center; }"
    )

    def handle_import() -> Awaitable[None] | None:
        nav.highlight(_IMPORT_KEY)
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
    if on_about is not None:
        nav.views[_ABOUT_KEY] = on_about
    if on_help is not None:
        nav.views[_HELP_KEY] = on_help

    left.clear()
    with left:
        import_button = (
            ui.button("Import", color=None, on_click=handle_import)
            .classes("w-44 text-sm")
            .props("dense")
        )
        nav.buttons[_IMPORT_KEY] = import_button
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
            if on_source_file is not None:
                nav.views[key] = partial(on_source_file, source_file.id)

        ui.space()
        with ui.column().classes("items-center gap-2 pb-4"):
            for key, text in ((_ABOUT_KEY, "About"), (_HELP_KEY, "Help")):
                button = (
                    ui.button(text, color=None).classes("w-44 text-sm").props("dense")
                )
                button.on_click(lambda key=key: nav.select(key))
                nav.buttons[key] = button

    return nav
