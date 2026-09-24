from dataclasses import dataclass

from nicegui import ui
from nicegui.element import Element


@dataclass
class ShellPanes:
    left: Element
    middle: Element
    right: Element


def shell() -> ShellPanes:
    with ui.row().classes("w-full h-screen no-wrap gap-0"):
        left = ui.column().classes("w-56 h-full border-r")
        with left:
            ui.label("Navigation")

        middle = ui.column().classes("flex-grow h-full")
        with middle:
            ui.label("Content")

        right = ui.column().classes("w-52 h-full border-l")
        with right:
            ui.label("Actions")

    return ShellPanes(left=left, middle=middle, right=right)
