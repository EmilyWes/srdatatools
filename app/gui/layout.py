from dataclasses import dataclass

from nicegui import ui
from nicegui.element import Element


@dataclass
class ShellPanes:
    left: Element
    middle: Element
    right: Element


def shell() -> ShellPanes:
    ui.query(".nicegui-content").classes("min-h-screen p-0 gap-0")
    with ui.row().classes("w-full flex-grow no-wrap gap-0 border items-stretch"):
        left = ui.column().classes("w-56 border-r items-center bg-grey-2 pt-4")
        with left:
            ui.label("Navigation")

        middle = ui.column().classes("flex-grow")
        with middle:
            ui.label("Content")

        right = ui.column().classes("w-52 border-l bg-grey-2")
        with right:
            ui.label("Actions")

    return ShellPanes(left=left, middle=middle, right=right)
