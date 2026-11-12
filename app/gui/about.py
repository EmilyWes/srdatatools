from importlib.metadata import PackageNotFoundError, metadata

from nicegui import ui
from nicegui.element import Element

from app.db.session import project_root

PACKAGE = "srdatatools"
REPOSITORY_URL = "https://github.com/EmilyWes/srdatatools"
LICENSE_FILE = "LICENSE"
THIRD_PARTY_FILE = "THIRD_PARTY_LICENSES.txt"
THIRD_PARTY_SUMMARY_FILE = "THIRD_PARTY_SUMMARY.txt"
HELP_PLACEHOLDER = "Help will be added later."
_TITLE_CLASSES = "text-lg font-bold"
_HEADING_CLASSES = "text-sm font-bold pt-2"
_TEXT_BOX_CLASSES = "w-full h-64 border rounded-borders"
_EXPANSION_CLASSES = "w-full text-sm"


def _version_and_summary() -> tuple[str, str]:
    try:
        info = metadata(PACKAGE)
    except PackageNotFoundError:
        return "unknown", ""
    return info["Version"], info["Summary"] or ""


def _text_box(text: str) -> None:
    with ui.scroll_area().classes(_TEXT_BOX_CLASSES):
        ui.label(text).classes("whitespace-pre-wrap font-mono text-xs")


def render_about_view(middle: Element) -> None:
    version, summary = _version_and_summary()
    root = project_root()
    middle.clear()
    with middle, ui.column().classes("w-full max-w-3xl gap-1 p-4"):
        ui.label(PACKAGE).classes(_TITLE_CLASSES)
        ui.label(f"Version {version}").classes("text-sm text-grey-7")
        if summary:
            ui.label(summary).classes("text-sm")
        ui.link(REPOSITORY_URL, REPOSITORY_URL, new_tab=True).classes("text-sm")
        with ui.expansion("License").classes(_EXPANSION_CLASSES):
            _text_box((root / LICENSE_FILE).read_text(encoding="utf-8"))
        ui.label("Third-party software").classes(_HEADING_CLASSES)
        _text_box((root / THIRD_PARTY_SUMMARY_FILE).read_text(encoding="utf-8"))
        with ui.expansion("Full license texts").classes(_EXPANSION_CLASSES):
            _text_box((root / THIRD_PARTY_FILE).read_text(encoding="utf-8"))


def render_help_view(middle: Element) -> None:
    middle.clear()
    with middle, ui.column().classes("w-full gap-1 p-4"):
        ui.label("Help").classes(_TITLE_CLASSES)
        ui.label(HELP_PLACEHOLDER).classes("text-sm")
