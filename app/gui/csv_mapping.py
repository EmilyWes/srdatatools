import re
from collections.abc import Callable
from dataclasses import dataclass, field

from nicegui import ui
from nicegui.element import Element

from app.parsers.csv_ import SCALAR_FIELDS, ColumnMapping, suggest_mapping

_IGNORE = "ignore"
_AUTHORS = "authors"
_KEYWORDS = "keywords"
_DATE = "date"
_YEAR = "year"
_MONTH = "month"
_DAY = "day"
_OTHER_ID = "other_id"

_EXCLUSIVE_TARGETS = (_DATE, _YEAR, _MONTH, _DAY)

_BASE_TARGET_KEYS = (_IGNORE, *sorted(SCALAR_FIELDS), _AUTHORS, _KEYWORDS, _OTHER_ID)
_ALL_TARGET_KEYS = (*_BASE_TARGET_KEYS, *_EXCLUSIVE_TARGETS)

_FIELD_LABELS: dict[str, str] = {
    "doi": "DOI",
    "issn": "ISSN",
    "isbn": "ISBN",
    "pmid": "PMID",
}

_SPECIAL_LABELS: dict[str, str] = {
    _IGNORE: "Ignore",
    _AUTHORS: "Authors",
    _KEYWORDS: "Keywords",
    _DATE: "Date (full)",
    _YEAR: "Year",
    _MONTH: "Month",
    _DAY: "Day",
    _OTHER_ID: "Other ID",
}


def _option_label(key: str) -> str:
    if key in _SPECIAL_LABELS:
        return _SPECIAL_LABELS[key]
    return _FIELD_LABELS.get(key, key.replace("_", " ").capitalize())


def _slugify(header: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return slug or "id"


def _suggestion_to_target(suggestion: str | None) -> str:
    if suggestion is None:
        return _IGNORE
    if suggestion == "other_ids":
        return _OTHER_ID
    if suggestion in SCALAR_FIELDS or suggestion in (
        _AUTHORS,
        _KEYWORDS,
        _DATE,
        _YEAR,
        _MONTH,
        _DAY,
    ):
        return suggestion
    return _IGNORE


def _exclusive_available(header: str, target: str, taken: dict[str, str]) -> bool:
    if taken.get(_DATE) not in (None, header):
        return False
    if target == _DATE:
        return all(taken.get(t) in (None, header) for t in (_YEAR, _MONTH, _DAY))
    return taken.get(target) in (None, header)


@dataclass
class _Row:
    header: str
    select: ui.select
    key_input: ui.input


@dataclass
class CsvMappingScreen:
    middle: Element
    on_confirm: Callable[[ColumnMapping], None]
    rows: list[_Row] = field(default_factory=list)
    list_delimiter_input: ui.input | None = None

    def _row_for(self, header: str) -> _Row:
        return next(row for row in self.rows if row.header == header)

    def _on_row_changed(self, row: _Row) -> None:
        row.key_input.set_visibility(row.select.value == _OTHER_ID)
        self._refresh_options()

    def _refresh_options(self) -> None:
        taken: dict[str, str] = {}
        for row in self.rows:
            if row.select.value in _EXCLUSIVE_TARGETS:
                taken[row.select.value] = row.header

        for row in self.rows:
            keys = list(_BASE_TARGET_KEYS) + [
                target
                for target in _EXCLUSIVE_TARGETS
                if _exclusive_available(row.header, target, taken)
            ]
            row.select.set_options({key: _option_label(key) for key in keys})

    def set_target(self, header: str, target: str) -> None:
        row = self._row_for(header)
        row.select.value = target
        self._on_row_changed(row)

    def set_other_id_key(self, header: str, key: str) -> None:
        self._row_for(header).key_input.value = key

    def available_targets(self, header: str) -> set[str]:
        return set(self._row_for(header).select.options)

    def confirm(self) -> None:
        self.on_confirm(self.current_mapping())

    def current_mapping(self) -> ColumnMapping:
        fields: dict[str, str] = {}
        authors_columns: list[str] = []
        keywords_columns: list[str] = []
        date_column: str | None = None
        year_column: str | None = None
        month_column: str | None = None
        day_column: str | None = None

        for row in self.rows:
            target = row.select.value
            if target == _IGNORE:
                continue
            elif target == _AUTHORS:
                authors_columns.append(row.header)
            elif target == _KEYWORDS:
                keywords_columns.append(row.header)
            elif target == _DATE:
                date_column = row.header
            elif target == _YEAR:
                year_column = row.header
            elif target == _MONTH:
                month_column = row.header
            elif target == _DAY:
                day_column = row.header
            elif target == _OTHER_ID:
                key = row.key_input.value.strip() or _slugify(row.header)
                fields[row.header] = f"other_ids.{key}"
            else:
                fields[row.header] = target

        delimiter = (
            self.list_delimiter_input.value if self.list_delimiter_input else ";"
        )
        return ColumnMapping(
            fields=fields,
            authors_columns=authors_columns,
            keywords_columns=keywords_columns,
            list_delimiter=delimiter or ";",
            date_column=date_column,
            year_column=year_column,
            month_column=month_column,
            day_column=day_column,
        )


def render_csv_mapping(
    middle: Element,
    headers: list[str],
    on_confirm: Callable[[ColumnMapping], None],
    show_confirm_button: bool = True,
) -> CsvMappingScreen:
    screen = CsvMappingScreen(middle=middle, on_confirm=on_confirm)

    suggestions = suggest_mapping(headers)
    taken: dict[str, str] = {}
    initial_targets: dict[str, str] = {}
    for header in headers:
        target = _suggestion_to_target(suggestions.get(header))
        if target in _EXCLUSIVE_TARGETS:
            if target in taken:
                target = _IGNORE
            else:
                taken[target] = header
        initial_targets[header] = target

    middle.clear()
    with middle:
        with ui.column().classes("gap-0 border rounded-borders"):
            header_classes = "w-full items-center gap-1 pl-6 py-2 bg-grey-2 border-b"
            with ui.row().classes(header_classes):
                ui.label("Input").classes("w-48 text-xs font-bold")
                ui.label("Mapping").classes("flex-grow text-xs font-bold")
            for i, header in enumerate(headers):
                row_classes = "w-full items-center gap-1 pl-6 py-0 border-b"
                if i % 2 == 1:
                    row_classes += " bg-grey-1"
                with ui.row().classes(row_classes):
                    ui.label(header).classes("w-48 truncate text-xs")
                    select = (
                        ui.select(
                            {key: _option_label(key) for key in _ALL_TARGET_KEYS},
                            value=initial_targets[header],
                        )
                        .classes("w-40 text-xs")
                        .props("dense options-dense outlined")
                    )
                    key_input = (
                        ui.input(value=_slugify(header))
                        .classes("w-32 text-xs")
                        .props("dense")
                    )
                    key_input.set_visibility(initial_targets[header] == _OTHER_ID)

                row = _Row(header=header, select=select, key_input=key_input)
                screen.rows.append(row)
                select.on_value_change(lambda _e, row=row: screen._on_row_changed(row))

        screen.list_delimiter_input = (
            ui.input("List delimiter", value=";").classes("pl-6 text-xs").props("dense")
        )
        if show_confirm_button:
            ui.button("Confirm", on_click=screen.confirm).classes("ml-6")

    screen._refresh_options()
    return screen
