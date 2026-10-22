import json
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui
from nicegui.element import Element
from nicegui.events import GenericEventArguments
from sqlalchemy.orm import Session

from app.db.models import Record
from app.db.settings import delete_setting, get_setting, set_setting
from app.gui.library_overview import source_label

_COLUMNS_KEY = "table_columns"
_NUMBER_COLUMNS = {"publication_year", "publication_month", "publication_day"}
_WIDE_COLUMNS = {"title", "abstract", "notes"}

COLUMNS: dict[str, str] = {
    "doi": "DOI",
    "title": "Title",
    "authors": "Authors",
    "publication_year": "Year",
    "journal": "Journal",
    "sources": "Sources",
    "abstract": "Abstract",
    "publication_month": "Month",
    "publication_day": "Day",
    "conference_name": "Conference",
    "volume": "Volume",
    "issue": "Issue",
    "pages": "Pages",
    "pmid": "PMID",
    "issn": "ISSN",
    "isbn": "ISBN",
    "other_ids": "Other IDs",
    "publication_type": "Publication type",
    "keywords": "Keywords",
    "language": "Language",
    "publisher": "Publisher",
    "url": "URL",
    "notes": "Notes",
}
DEFAULT_COLUMNS = ["doi", "title", "authors", "publication_year", "journal", "sources"]


@dataclass
class RecordSelection:
    ids: set[int] = field(default_factory=set)

    def replace(self, rows: Sequence[dict[str, Any]]) -> None:
        self.ids = {row["id"] for row in rows}


def _in_display_order(columns: Collection[str]) -> list[str]:
    return [key for key in COLUMNS if key in columns]


def load_columns(session: Session) -> list[str]:
    stored = get_setting(session, _COLUMNS_KEY)
    return (
        _in_display_order(json.loads(stored)) if stored is not None else DEFAULT_COLUMNS
    )


def save_columns(session: Session, columns: Sequence[str]) -> None:
    set_setting(session, _COLUMNS_KEY, json.dumps(_in_display_order(columns)))


def reset_columns(session: Session) -> None:
    delete_setting(session, _COLUMNS_KEY)


def _author_name(author: dict[str, Any]) -> str:
    if author.get("full_name"):
        return str(author["full_name"])
    parts = [author.get("family_name"), author.get("given_name")]
    return ", ".join(part for part in parts if part)


def _authors(authors: list[dict[str, Any]]) -> str:
    if not authors:
        return ""
    first = _author_name(authors[0])
    return f"{first} et al." if len(authors) > 1 else first


def _sources(record: Record) -> str:
    labels = [source_label(rs.source_file.source) for rs in record.sources]
    return ", ".join(dict.fromkeys(labels))


def row_for(record: Record) -> dict[str, Any]:
    row: dict[str, Any] = {"id": record.id}
    for key in COLUMNS:
        if key == "sources":
            row[key] = _sources(record)
        elif key == "authors":
            row[key] = _authors(record.authors)
        else:
            value = getattr(record, key)
            if isinstance(value, list):
                value = "; ".join(value)
            elif isinstance(value, dict):
                value = "; ".join(f"{name}: {id_}" for name, id_ in value.items())
            row[key] = value
    return row


def _column_def(key: str) -> dict[str, Any]:
    return {
        "field": key,
        "headerName": COLUMNS[key],
        "width": 400 if key in _WIDE_COLUMNS else 160,
        "filter": (
            "agNumberColumnFilter" if key in _NUMBER_COLUMNS else "agTextColumnFilter"
        ),
    }


def render_record_table(
    middle: Element,
    records: Sequence[Record],
    columns: Sequence[str],
    selection: RecordSelection,
) -> None:
    selection.ids &= {record.id for record in records}

    def count_text() -> str:
        return f"{len(selection.ids)} selected"

    middle.clear()
    with middle:
        with ui.column().classes("w-full h-screen p-4 gap-2 no-wrap"):
            with ui.row().classes("items-center gap-2"):
                select_filtered = ui.button("Select all filtered", color=None)
                clear = ui.button("Clear selection", color=None)
                count = ui.label(count_text()).classes("text-sm text-grey-7")
            grid = ui.aggrid(
                {
                    "columnDefs": [_column_def(key) for key in columns],
                    "rowData": [row_for(record) for record in records],
                    "defaultColDef": {"sortable": True, "resizable": True},
                    ":getRowId": "(params) => String(params.data.id)",
                    "rowSelection": {
                        "mode": "multiRow",
                        "checkboxes": True,
                        "headerCheckbox": False,
                        "enableClickSelection": False,
                    },
                    "initialState": {
                        "rowSelection": [str(id_) for id_ in sorted(selection.ids)]
                    },
                },
                auto_size_columns=False,
            ).classes("w-full flex-grow")

    for button in (select_filtered, clear):
        button.classes("text-sm").props("dense")
    select_filtered.on_click(lambda: grid.run_grid_method("selectAll", "filtered"))
    clear.on_click(lambda: grid.run_grid_method("deselectAll"))

    async def sync_selection(_: GenericEventArguments) -> None:
        selection.replace(await grid.get_selected_rows())
        count.text = count_text()

    grid.on("selectionChanged", sync_selection)


def render_table_settings(
    middle: Element,
    columns: Sequence[str],
    on_change: Callable[[list[str]], Any],
    on_restore: Callable[[], Any],
    on_back: Callable[[], Any],
) -> None:
    selected = set(columns)

    def toggle(key: str, checked: bool) -> None:
        if checked:
            selected.add(key)
        else:
            selected.discard(key)
        on_change(_in_display_order(selected))

    middle.clear()
    with middle:
        with ui.column().classes("w-full p-4 gap-2"):
            ui.label("Table settings").classes("text-lg")
            ui.label("Columns").classes("text-sm text-grey-7")
            with ui.column().classes("gap-0"):
                for key, label in COLUMNS.items():
                    ui.checkbox(
                        label,
                        value=key in selected,
                        on_change=lambda e, key=key: toggle(key, e.value),
                    ).props("dense")
            with ui.row().classes("gap-2 pt-2"):
                ui.button("Restore defaults", color=None, on_click=on_restore).classes(
                    "text-sm"
                ).props("dense")
                ui.button("Back to table", color=None, on_click=on_back).classes(
                    "text-sm"
                ).props("dense")
