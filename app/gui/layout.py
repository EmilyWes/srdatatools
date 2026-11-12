from dataclasses import dataclass

from nicegui import ui
from nicegui.element import Element


@dataclass
class ShellPanes:
    left: Element
    middle: Element
    right: Element


def shell() -> ShellPanes:
    # One screen high: only the middle pane scrolls, so the side panes' bottom
    # buttons stay in view.
    ui.query(".nicegui-content").classes("h-screen p-0 gap-0")
    with ui.row().classes(
        "w-full flex-grow min-h-0 no-wrap gap-0 border items-stretch"
    ):
        left = ui.column().classes("w-56 border-r items-center bg-grey-2 pt-4")
        middle = ui.column().classes("flex-grow min-w-0 overflow-y-auto")
        right = ui.column().classes("w-56 border-l bg-grey-2")

    return ShellPanes(left=left, middle=middle, right=right)
