from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui
from nicegui.element import Element

from app.db.models import SourceFile

_SELECTED_CLASS = "bg-blue-100"
_IMPORT_KEY = "import"
_LIBRARY_KEY = "library"


@dataclass
class LeftPanelNav:
    middle: Element
    buttons: dict[str, ui.button] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    selected_key: str | None = None

    def show_placeholder(self, label: str) -> None:
        self.middle.clear()
        with self.middle:
            ui.label(label)

    def select(self, key: str) -> None:
        if self.selected_key is not None:
            self.buttons[self.selected_key].classes(remove=_SELECTED_CLASS)
        self.buttons[key].classes(add=_SELECTED_CLASS)
        self.selected_key = key
        self.show_placeholder(self.labels[key])


def render_left_panel(
    left: Element,
    middle: Element,
    source_files: Sequence[SourceFile],
    on_import: Callable[[], Awaitable[Any]] | None = None,
) -> LeftPanelNav:
    nav = LeftPanelNav(middle=middle)

    def handle_import() -> Any:
        nav.select(_IMPORT_KEY)
        return on_import() if on_import is not None else None

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

        library_button = (
            ui.button("Library", color=None).classes("w-44 text-sm").props("dense")
        )
        library_button.on_click(lambda: nav.select(_LIBRARY_KEY))
        nav.buttons[_LIBRARY_KEY] = library_button
        nav.labels[_LIBRARY_KEY] = "Library"

        if source_files:
            ui.separator()
            ui.label("Imported files").classes(
                "w-44 text-xs text-grey-6 pt-1 text-center"
            )

        for source_file in source_files:
            key = f"source_file:{source_file.id}"
            button = (
                ui.button(source_file.filename, color=None)
                .classes("w-44 text-sm")
                .props("dense")
            )
            button.on_click(lambda key=key: nav.select(key))
            nav.buttons[key] = button
            nav.labels[key] = source_file.filename

    return nav
