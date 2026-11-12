import json
from collections.abc import (
    Awaitable,
    Callable,
    Collection,
    Iterable,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from typing import Any, cast

from nicegui import ui
from nicegui.element import Element
from nicegui.events import GenericEventArguments
from sqlalchemy.orm import Session

from app.db.queries import (
    list_keyword_prefixes,
    list_label_columns,
    list_record_labels,
    list_record_rows,
    list_record_sources,
)
from app.db.settings import delete_setting, get_setting, set_setting
from app.gui.format import (
    LabelFormat,
    format_count,
    is_keyword_key,
    is_label_key,
    keyword_key,
    keyword_prefix,
    label_key,
    label_pair,
    label_text,
    source_label,
)
from app.parsers.mapping import split_keyword

_COLUMNS_KEY = "table_columns"
_NUMBER_COLUMNS = {"publication_year", "publication_month", "publication_day"}
_WIDE_COLUMNS = {"title", "abstract", "notes"}
_SELECTION_TIMEOUT = 10.0
_ROW_HEIGHT = 24
_TABLE_CLASS = "record-table"
_HEADER_CSS = (
    f".{_TABLE_CLASS} .ag-header-cell {{ cursor: pointer; }}"
    f" .{_TABLE_CLASS} .ag-header-cell:hover"
    " { background-color: rgba(0, 0, 0, 0.06); }"
)
_LABEL_FORMAT_KEY = "table_label_format"

_LABEL_FORMATS: dict[LabelFormat, str] = {"numbers": "Numbers", "words": "Words"}

COLUMNS: dict[str, str] = {
    "doi": "DOI",
    "title": "Title",
    "author_names": "Authors",
    "publication_year": "Publication year",
    "journal": "Journal",
    "sources": "Sources",
    "abstract": "Abstract",
    "author_ids": "Author IDs",
    "author_affiliations": "Affiliations",
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
DEFAULT_COLUMNS = ["doi", "title", "author_names"]


@dataclass
class RecordSelection:
    ids: set[int] = field(default_factory=set)

    def replace(self, ids: Iterable[int]) -> None:
        self.ids = set(ids)


def column_field(key: str) -> str:
    """ag-grid reads dots in a field as a nested path, so label and keyword keys are
    hex-encoded."""
    if is_label_key(key):
        return f"label_{key.encode().hex()}"
    if is_keyword_key(key):
        return f"keywords_{key.encode().hex()}"
    return key


def _header(key: str) -> str:
    if is_label_key(key):
        phase, screener = label_pair(key)
        return f"Label: {phase} / {screener}"
    if is_keyword_key(key):
        return f"Keywords: {keyword_prefix(key)}"
    return COLUMNS[key]


def _in_display_order(
    columns: Collection[str], extra_columns: Sequence[str]
) -> list[str]:
    fixed = [key for key in COLUMNS if key in columns]
    return fixed + [key for key in extra_columns if key in columns]


def load_label_columns(session: Session) -> list[str]:
    return [label_key(*pair) for pair in list_label_columns(session)]


def load_keyword_columns(session: Session) -> list[str]:
    return [keyword_key(prefix) for prefix in list_keyword_prefixes(session)]


def load_columns(session: Session) -> list[str]:
    stored = get_setting(session, _COLUMNS_KEY)
    if stored is None:
        return DEFAULT_COLUMNS
    return _in_display_order(
        json.loads(stored),
        load_label_columns(session) + load_keyword_columns(session),
    )


def save_columns(session: Session, columns: Sequence[str]) -> None:
    extra_columns = [key for key in columns if is_label_key(key)] + [
        key for key in columns if is_keyword_key(key)
    ]
    set_setting(
        session, _COLUMNS_KEY, json.dumps(_in_display_order(columns, extra_columns))
    )


def reset_columns(session: Session) -> None:
    delete_setting(session, _COLUMNS_KEY)


def load_label_format(session: Session) -> LabelFormat:
    return cast(LabelFormat, get_setting(session, _LABEL_FORMAT_KEY) or "numbers")


def save_label_format(session: Session, label_format: LabelFormat) -> None:
    set_setting(session, _LABEL_FORMAT_KEY, label_format)


def reset_label_format(session: Session) -> None:
    delete_setting(session, _LABEL_FORMAT_KEY)


def _sources(sources: Sequence[str | None]) -> str:
    return ", ".join(dict.fromkeys(source_label(source) for source in sources))


def row_for(values: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, list):
            value = "; ".join(value)
        elif isinstance(value, dict):
            value = "; ".join(f"{name}: {id_}" for name, id_ in value.items())
        row[key] = value
    return row


def load_rows(
    session: Session, columns: Sequence[str], label_format: LabelFormat = "numbers"
) -> list[dict[str, Any]]:
    label_columns = [key for key in columns if is_label_key(key)]
    keyword_columns = [key for key in columns if is_keyword_key(key)]
    fields = [
        key for key in columns if key in COLUMNS and key not in ("sources", "keywords")
    ]
    if "keywords" in columns or keyword_columns:
        fields.append("keywords")
    rows = []
    for record in list_record_rows(session, fields):
        keywords = [split_keyword(keyword) for keyword in record.pop("keywords", [])]
        row = row_for(record)
        if "keywords" in columns:
            row["keywords"] = "; ".join(
                text for prefix, text in keywords if prefix is None
            )
        for key in keyword_columns:
            row[column_field(key)] = "; ".join(
                text for prefix, text in keywords if prefix == keyword_prefix(key)
            )
        rows.append(row)
    if "sources" in columns:
        sources = list_record_sources(session)
        for row in rows:
            row["sources"] = _sources(sources.get(row["id"], []))
    if label_columns:
        labels = list_record_labels(session)
        for row in rows:
            pairs = labels.get(row["id"], {})
            for key in label_columns:
                values = pairs.get(label_pair(key), [])
                row[column_field(key)] = "; ".join(
                    label_text(value, label_format) for value in values
                )
    return rows


def _column_def(key: str) -> dict[str, Any]:
    return {
        "field": column_field(key),
        "headerName": _header(key),
        "headerTooltip": _header(key),
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
    on_delete: Callable[[set[int]], Awaitable[None] | None] | None = None,
) -> None:
    selection.ids &= {row["id"] for row in rows}

    def open_delete_dialog() -> None:
        count = format_count(len(selection.ids))
        delete_message.text = f"Delete {count} records? This can't be undone."
        delete_dialog.open()

    def delete() -> Awaitable[None] | None:
        delete_dialog.close()
        return None if on_delete is None else on_delete(set(selection.ids))

    def count_line(text: str, count: int) -> ui.label:
        ui.label(f"{text}:").classes("text-sm")
        return ui.label(format_count(count)).classes("text-sm")

    middle.clear()
    with middle:
        with ui.column().classes("w-full h-screen p-6 gap-3 no-wrap"):
            with ui.grid(columns="max-content 5rem max-content max-content").classes(
                "items-center gap-x-2 gap-y-1"
            ):
                count_line("Total number of rows", len(rows))
                ui.element("div")
                ui.element("div")
                filter_count = count_line("Rows in filter", len(rows))
                clear_filters = ui.button("Clear all filters", color=None).props(
                    "outline"
                )
                ui.element("div")
                selection_count = count_line("Rows in selection", len(selection.ids))
                clear_selection = ui.button("Clear selection", color=None).props(
                    "outline"
                )
                delete_selected = ui.button(
                    "Delete selected", color="negative", on_click=open_delete_dialog
                )
            grid = ui.aggrid(
                {
                    "columnDefs": [_column_def(key) for key in columns],
                    "rowData": list(rows),
                    "defaultColDef": {
                        "sortable": True,
                        "resizable": True,
                        "cellStyle": {"fontSize": "12px"},
                    },
                    "rowHeight": _ROW_HEIGHT,
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
            ).classes(f"w-full flex-grow {_TABLE_CLASS}")
            with ui.dialog() as delete_dialog, ui.card():
                delete_message = ui.label()
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", color=None, on_click=delete_dialog.close).props(
                        "flat no-caps"
                    )
                    ui.button("Delete", color="negative", on_click=delete)
        ui.add_css(_HEADER_CSS)

    delete_selected.set_enabled(bool(selection.ids))
    for button in (clear_filters, clear_selection, delete_selected):
        button.classes("text-sm").props("dense no-caps unelevated")
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
        delete_selected.set_enabled(bool(selection.ids))

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
    keyword_columns: Sequence[str] = (),
) -> None:
    selected = set(columns)
    extra_columns = [*label_columns, *keyword_columns]

    def toggle(key: str, checked: bool) -> None:
        if checked:
            selected.add(key)
        else:
            selected.discard(key)
        on_change(_in_display_order(selected, extra_columns))

    middle.clear()
    with middle:
        with ui.column().classes("w-full p-6 gap-2"):
            ui.label("Table settings").classes("text-2xl")
            ui.label("Columns").classes("title-small pt-2")
            with ui.column().classes("gap-0"):
                for key in [*COLUMNS, *extra_columns]:
                    ui.checkbox(
                        _header(key),
                        value=key in selected,
                        on_change=lambda e, key=key: toggle(key, e.value),
                    ).props("dense")
            ui.label("Label values").classes("title-small pt-3")
            ui.radio(
                dict(_LABEL_FORMATS),
                value=label_format,
                on_change=lambda e: on_label_format(e.value),
            ).props("dense inline")
            with ui.row().classes("gap-2 pt-2"):
                ui.button("Restore defaults", color=None, on_click=on_restore).props(
                    "outline no-caps"
                )
                ui.button("Back to table", color=None, on_click=on_back).props(
                    "outline no-caps"
                )
