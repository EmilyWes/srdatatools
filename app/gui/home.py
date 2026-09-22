from importlib.metadata import version

from nicegui import ui


@ui.page("/")
def home() -> None:
    ui.label("srdatatools").classes("text-h4")
    ui.label(f"v{version('srdatatools')}")
