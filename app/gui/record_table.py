import json
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from nicegui import ui
from nicegui.element import Element
from nicegui.events import GenericEventArguments
from sqlalchemy.orm import Session

from app.db.queries import (
    list_label_columns,
    list_record_labels,
    list_record_rows,
    list_record_sources,
)
from app.db.settings import delete_setting, get_setting, set_setting
from app.gui.library_overview import format_count, source_label

_COLUMNS_KEY = "table_columns"
_NUMBER_COLUMNS = {"publication_year", "publication_month", "publication_day"}
_WIDE_COLUMNS = {"title", "abstract", "notes"}
_SELECTION_TIMEOUT = 10.0
_LABEL_PREFIX = "label:"
_LABEL_FORMAT_KEY = "table_label_format"

LabelFormat = Literal["words", "numbers"]
_LABEL_FORMATS: dict[LabelFormat, str] = {"words": "Words", "numbers": "Numbers"}
_LABEL_NUMBERS = {
    "include": "1",
    "exclude": "0",
    "maybe": "0.5",
    "unknown": "?",
    "unlabeled": "-1",
}

COLUMNS: dict[str, str] = {
    "doi": "DOI",
    "title": "Title",
    "authors": "Authors",
    "publication_year": "Publication year",
    "journal": "Journal",
    "sources": "Sources",
    "abstract": "Abstract",
    "publication_month": "Publication month",
    "publication_day": "Publication day",
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

    def replace(self, ids: Iterable[int]) -> None:
        self.ids = set(ids)


def label_column_key(phase: str, screener: str) -> str:
    return _LABEL_PREFIX + json.dumps([phase, screener])


def _is_label_column(key: str) -> bool:
    return key.startswith(_LABEL_PREFIX)


def _label_pair(key: str) -> tuple[str, str]:
    phase, screener = json.loads(key.removeprefix(_LABEL_PREFIX))
    return phase, screener


def label_field(key: str) -> str:
    """ag-grid reads dots in a field as a nested path, so label keys are hex-encoded."""
    return f"label_{key.encode().hex()}" if _is_label_column(key) else key


def _header(key: str) -> str:
    if _is_label_column(key):
        phase, screener = _label_pair(key)
        return f"Label: {phase} / {screener}"
    return COLUMNS[key]


def _in_display_order(
    columns: Collection[str], label_columns: Sequence[str]
) -> list[str]:
    fixed = [key for key in COLUMNS if key in columns]
    return fixed + [key for key in label_columns if key in columns]


def load_label_columns(session: Session) -> list[str]:
    return [label_column_key(*pair) for pair in list_label_columns(session)]


def load_columns(session: Session) -> list[str]:
    stored = get_setting(session, _COLUMNS_KEY)
    if stored is None:
        return DEFAULT_COLUMNS
    return _in_display_order(json.loads(stored), load_label_columns(session))


def save_columns(session: Session, columns: Sequence[str]) -> None:
    label_columns = [key for key in columns if _is_label_column(key)]
    set_setting(
        session, _COLUMNS_KEY, json.dumps(_in_display_order(columns, label_columns))
    )


def reset_columns(session: Session) -> None:
    delete_setting(session, _COLUMNS_KEY)


def load_label_format(session: Session) -> LabelFormat:
    return cast(LabelFormat, get_setting(session, _LABEL_FORMAT_KEY) or "words")


def save_label_format(session: Session, label_format: LabelFormat) -> None:
    set_setting(session, _LABEL_FORMAT_KEY, label_format)


def reset_label_format(session: Session) -> None:
    delete_setting(session, _LABEL_FORMAT_KEY)


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


def _sources(sources: Sequence[str | None]) -> str:
    return ", ".join(dict.fromkeys(source_label(source) for source in sources))


def row_for(values: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in values.items():
        if key == "authors":
            value = _authors(value)
        elif isinstance(value, list):
            value = "; ".join(value)
        elif isinstance(value, dict):
            value = "; ".join(f"{name}: {id_}" for name, id_ in value.items())
        row[key] = value
    return row


def load_rows(
    session: Session, columns: Sequence[str], label_format: LabelFormat = "words"
) -> list[dict[str, Any]]:
    label_columns = [key for key in columns if _is_label_column(key)]
    fields = [key for key in columns if key != "sources" and key not in label_columns]
    rows = [row_for(values) for values in list_record_rows(session, fields)]
    if "sources" in columns:
        sources = list_record_sources(session)
        for row in rows:
            row["sources"] = _sources(sources.get(row["id"], []))
    if label_columns:
        labels = list_record_labels(session)
        for row in rows:
            pairs = labels.get(row["id"], {})
            for key in label_columns:
                values = pairs.get(_label_pair(key), [])
                if label_format == "numbers":
                    values = [_LABEL_NUMBERS[value] for value in values]
                row[label_field(key)] = "; ".join(values)
    return rows


def _column_def(key: str) -> dict[str, Any]:
    return {
        "field": label_field(key),
        "headerName": _header(key),
        "width": 400 if key in _WIDE_COLUMNS else 160,
        "filter": (
            "agNumberColumnFilter" if key in _NUMBER_COLUMNS else "agTextColumnFilter"
        ),
    }


def render_record_table(
    middle: Element,
    rows: Sequence[dict[str, Any]],
    columns: Sequence[str],
    selection: RecordSelection,
) -> None:
    selection.ids &= {row["id"] for row in rows}

    def count_line(text: str, count: int) -> ui.label:
        ui.label(f"{text}:").classes("text-sm")
        return ui.label(format_count(count)).classes("text-sm")

    middle.clear()
    with middle:
        with ui.column().classes("w-full h-screen p-4 gap-2 no-wrap"):
            with ui.grid(columns="max-content 5rem max-content").classes(
                "items-center gap-x-2 gap-y-1"
            ):
                count_line("Total number of rows", len(rows))
                ui.element("div")
                filter_count = count_line("Rows in filter", len(rows))
                clear_filters = ui.button("Clear all filters", color=None)
                selection_count = count_line("Rows in selection", len(selection.ids))
                clear_selection = ui.button("Clear selection", color=None)
            grid = ui.aggrid(
                {
                    "columnDefs": [_column_def(key) for key in columns],
                    "rowData": list(rows),
                    "defaultColDef": {"sortable": True, "resizable": True},
                    ":getRowId": "(params) => String(params.data.id)",
                    "rowSelection": {
                        "mode": "multiRow",
                        "checkboxes": True,
                        "headerCheckbox": True,
                        "selectAll": "filtered",
                        "enableClickSelection": True,
                        "enableSelectionWithoutKeys": True,
                    },
                    "initialState": {
                        "rowSelection": [str(id_) for id_ in sorted(selection.ids)]
                    },
                },
                auto_size_columns=False,
            ).classes("w-full flex-grow")

    for button in (clear_filters, clear_selection):
        button.classes("text-sm").props("dense no-caps")
    clear_filters.on_click(lambda: grid.run_grid_method("setFilterModel", None))
    clear_selection.on_click(lambda: grid.run_grid_method("deselectAll"))

    async def sync_selection(_: GenericEventArguments) -> None:
        # Only ids are fetched: full row data for thousands of rows times out.
        ids = await grid.client.run_javascript(
            f"return getElement({grid.id}).api.getSelectedNodes()"
            ".map((node) => Number(node.id))",
            timeout=_SELECTION_TIMEOUT,
        )
        selection.replace(ids)
        selection_count.text = format_count(len(selection.ids))

    async def sync_filter_count(_: GenericEventArguments) -> None:
        count = await grid.run_grid_method("getDisplayedRowCount")
        filter_count.text = format_count(count)

    grid.on("selectionChanged", sync_selection)
    grid.on("filterChanged", sync_filter_count)


def render_table_settings(
    middle: Element,
    columns: Sequence[str],
    label_format: LabelFormat,
    on_change: Callable[[list[str]], Any],
    on_label_format: Callable[[LabelFormat], Any],
    on_restore: Callable[[], Any],
    on_back: Callable[[], Any],
    label_columns: Sequence[str] = (),
) -> None:
    selected = set(columns)

    def toggle(key: str, checked: bool) -> None:
        if checked:
            selected.add(key)
        else:
            selected.discard(key)
        on_change(_in_display_order(selected, label_columns))

    middle.clear()
    with middle:
        with ui.column().classes("w-full p-4 gap-2"):
            ui.label("Table settings").classes("text-lg")
            ui.label("Columns").classes("text-sm text-grey-7")
            with ui.column().classes("gap-0"):
                for key in [*COLUMNS, *label_columns]:
                    ui.checkbox(
                        _header(key),
                        value=key in selected,
                        on_change=lambda e, key=key: toggle(key, e.value),
                    ).props("dense")
            ui.label("Label values").classes("text-sm text-grey-7 pt-2")
            ui.radio(
                dict(_LABEL_FORMATS),
                value=label_format,
                on_change=lambda e: on_label_format(e.value),
            ).props("dense inline")
            with ui.row().classes("gap-2 pt-2"):
                ui.button("Restore defaults", color=None, on_click=on_restore).classes(
                    "text-sm"
                ).props("dense")
                ui.button("Back to table", color=None, on_click=on_back).classes(
                    "text-sm"
                ).props("dense")
