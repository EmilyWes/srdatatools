from collections.abc import Callable
from typing import Any

from nicegui import ui
from nicegui.element import Element

from app.db.models import SourceFile
from app.gui.library_overview import format_count, source_label


def render_source_file_view(
    middle: Element,
    source_file: SourceFile,
    records_in_library: int,
    on_remove: Callable[[], Any],
) -> None:
    def remove() -> None:
        dialog.close()
        on_remove()

    middle.clear()
    with middle:
        with ui.dialog() as dialog, ui.card():
            ui.label(
                f"Remove {source_file.filename} and its "
                f"{format_count(records_in_library)} records from the library? "
                "This cannot be undone."
            )
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", color=None, on_click=dialog.close).props("flat")
                ui.button("Remove", color="negative", on_click=remove)

        with ui.column().classes("w-full p-4 gap-4"):
            ui.label(source_file.filename).classes("text-lg")
            with ui.grid(columns="max-content auto").classes("gap-x-4 gap-y-1"):
                for name, value in [
                    ("Source", source_label(source_file.source)),
                    ("Format", source_file.format),
                    ("Imported at", f"{source_file.imported_at:%Y-%m-%d %H:%M}"),
                    ("Path", source_file.path or ""),
                ]:
                    ui.label(name).classes("text-sm text-grey-7")
                    ui.label(value).classes("text-sm")
            with ui.column().classes("gap-0"):
                ui.label("Records in library").classes("text-sm text-grey-7")
                ui.label(format_count(records_in_library)).classes("text-3xl")
            with ui.column().classes("gap-1"):
                ui.label(
                    f"Skipped on import: {format_count(len(source_file.skipped_rows))}"
                ).classes("text-sm text-grey-7")
                ui.table(
                    columns=[
                        {"name": "row", "label": "Row", "field": "row_number"},
                        {
                            "name": "reason",
                            "label": "Reason",
                            "field": "reason",
                            "align": "left",
                        },
                    ],
                    rows=source_file.skipped_rows,
                    pagination=0,
                ).props("dense flat bordered hide-bottom").classes("min-w-48")
            ui.button("Remove from library", color=None, on_click=dialog.open).classes(
                "text-sm"
            ).props("dense no-caps")
