from dataclasses import dataclass

from nicegui import ui
from nicegui.element import Element

from app.gui.theme import apply_theme

_SIDE_CLASSES = "w-60 shrink-0 surface-low outline-variant"


@dataclass
class ShellPanes:
    left: Element
    middle: Element
    right: Element


def _brand() -> None:
    with ui.row().classes("items-center gap-3 no-wrap px-5 pt-5 pb-3"):
        with ui.element("div").classes(
            "bg-primary rounded-xl w-9 h-9 flex items-center justify-center"
        ):
            ui.icon("dataset", size="20px").classes("text-black")
        ui.label("srdatatools").classes("text-lg font-medium tracking-tight")


def shell() -> ShellPanes:
    apply_theme()
    # One screen high: only the middle pane scrolls, so the side panes' bottom
    # buttons stay in view.
    ui.query(".nicegui-content").classes("h-screen p-0 gap-0")
    with ui.row().classes("w-full flex-grow min-h-0 no-wrap gap-0 items-stretch"):
        with ui.column().classes(f"{_SIDE_CLASSES} border-r gap-0 no-wrap"):
            _brand()
            left = ui.column().classes("w-full flex-grow min-h-0 no-wrap px-3 gap-1")
        middle = ui.column().classes("flex-grow min-w-0 overflow-y-auto")
        right = ui.column().classes(f"{_SIDE_CLASSES} border-l")

    return ShellPanes(left=left, middle=middle, right=right)
