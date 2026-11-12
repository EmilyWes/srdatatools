from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui
from nicegui.element import Element

from app.cleaning.options import CLEANING_BOXES, CleaningOptions
from app.gui.export_flow import records_count
from app.gui.import_flow import GRID_CLASSES, GRID_COLUMNS
from app.gui.quirks_overview import QuirksScreen, render_quirks_overview

OnClean = Callable[[CleaningOptions], Awaitable[None] | None]

_NO_RECORDS = "no records to clean"


@dataclass
class CleaningView:
    screen: QuirksScreen[CleaningOptions]
    run_button: ui.button


def render_cleaning_view(
    middle: Element,
    record_count: int,
    options: CleaningOptions,
    *,
    selected: bool,
    on_clean: OnClean,
) -> CleaningView:
    """Opens on the saved `options`; the blue tint and Restore defaults compare
    with the built-in defaults."""
    middle.clear()
    with middle, ui.column().classes("gap-4 pt-4 items-center w-full"):
        with ui.grid(columns=GRID_COLUMNS).classes(GRID_CLASSES):
            ui.label("Number of records:").classes("text-sm")
            ui.label(records_count(record_count, selected)).classes("text-sm")
        screen = render_quirks_overview(
            ui.column().classes("w-full"),
            CLEANING_BOXES,
            CleaningOptions(),
            start=options,
        )
        run_button = ui.button(
            "Run cleaning", on_click=lambda: on_clean(screen.current_choices())
        ).props("dense")
        if not record_count:
            run_button.disable()
            run_button.tooltip(_NO_RECORDS)
    return CleaningView(screen=screen, run_button=run_button)
