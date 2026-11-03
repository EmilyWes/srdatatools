from collections.abc import Awaitable, Callable

from nicegui import ui
from nicegui.element import Element

from app.db.models import SourceFile
from app.gui.import_flow import preview_for, row_defaults_for, type_label
from app.gui.library_overview import format_count, source_label
from app.gui.mapping_table import render_mapping_table
from app.gui.quirks_overview import render_quirks_overview
from app.parsers.common import FileSummary
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.overview import (
    default_choices,
    load_choices,
    quirk_boxes,
)

_VIEW_MAPPING = "mapping"
_VIEW_PARSING = "parsing"


def render_source_file_view(
    middle: Element,
    source_file: SourceFile,
    records_in_library: int,
    on_remove: Callable[[], Awaitable[None] | None],
) -> None:
    def remove() -> Awaitable[None] | None:
        dialog.close()
        return on_remove()

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
                details = [
                    ("Source", source_label(source_file.source)),
                    ("Format", source_file.format),
                    ("Imported at", f"{source_file.imported_at:%Y-%m-%d %H:%M}"),
                    ("Path", source_file.path or ""),
                ]
                if source_file.sheet is not None:
                    details.insert(2, ("Sheet", source_file.sheet))
                for name, value in details:
                    ui.label(name).classes("text-sm text-grey-7")
                    ui.label(value).classes("text-sm")
            with ui.row().classes("items-center gap-6"):
                with ui.column().classes("gap-0"):
                    ui.label("Records in library").classes("text-sm text-grey-7")
                    ui.label(format_count(records_in_library)).classes("text-3xl")
                ui.button(
                    "Remove from library", color=None, on_click=dialog.open
                ).classes("text-sm").props("dense no-caps")
            with ui.column().classes("w-full gap-1"):
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
                            "style": "white-space: normal; overflow-wrap: anywhere",
                        },
                    ],
                    rows=source_file.skipped_rows,
                    pagination=0,
                ).props("dense flat bordered hide-bottom").classes(
                    "min-w-48 max-w-full max-h-80"
                )
            with ui.column().classes("gap-1"):
                toggle = ui.toggle(
                    {_VIEW_MAPPING: "Mapping", _VIEW_PARSING: "Parsing"},
                    value=_VIEW_MAPPING,
                ).props("dense no-caps")
                summary = FileSummary(**source_file.file_summary)
                source = source_file.source or "unknown"
                choices = load_choices(
                    source_file.quirk_choices, source_file.format, source
                )
                mapping_container = ui.column()
                quirks_container = ui.column()
                quirks_container.set_visibility(False)
                render_mapping_table(
                    mapping_container,
                    summary,
                    FieldMapping.model_validate(source_file.suggested_mapping),
                    defaults=row_defaults_for(source_file.format, source),
                    preview=preview_for(
                        source_file.format, source, summary, lambda: choices
                    ),
                    chosen=FieldMapping.model_validate(source_file.field_mapping),
                )
                render_quirks_overview(
                    quirks_container,
                    quirk_boxes(source_file.format, type_label(source_file.format)),
                    default_choices(source_file.format, source),
                    chosen=choices,
                )

                def show(view: str) -> None:
                    mapping_container.set_visibility(view == _VIEW_MAPPING)
                    quirks_container.set_visibility(view == _VIEW_PARSING)

                toggle.on_value_change(lambda e: show(e.value))
