from nicegui import ui

from app.gui.layout import shell


@ui.page("/")
def home() -> None:
    shell()
