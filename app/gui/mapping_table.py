from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from nicegui import ui
from nicegui.element import Element

from app.models.record import Author, PartialDate, Record
from app.parsers.common import FileSummary
from app.parsers.mapping import (
    DATE_TARGETS,
    EXCLUSIVE_TARGETS,
    ISSN_ISBN_TARGET,
    LIST_TARGETS,
    OTHER_IDS_PREFIX,
    PAGE_TARGETS,
    SCALAR_FIELDS,
    FieldMapping,
    default_other_id_key,
)

_ROW_FIELD_CSS = """
.mapping-field .q-field__control, .mapping-field .q-field__marginal {
    min-height: 24px;
    height: 24px;
    align-items: center;
}
.mapping-field .q-field__control-container {
    padding-top: 0;
    align-items: center;
}
.mapping-field .q-field__native, .mapping-field .q-field__input {
    padding: 0;
    min-height: 0;
}
"""

_IGNORE = "ignore"
_OTHER_IDS = "other_ids"

_BASE_TARGET_KEYS = (
    _IGNORE,
    *sorted({*SCALAR_FIELDS, ISSN_ISBN_TARGET}),
    *LIST_TARGETS,
    _OTHER_IDS,
)
_ALL_TARGET_KEYS = (*_BASE_TARGET_KEYS, *EXCLUSIVE_TARGETS)

_LABELS: dict[str, str] = {
    "doi": "DOI",
    "issn": "ISSN",
    "isbn": "ISBN",
    ISSN_ISBN_TARGET: "ISSN/ISBN",
    "pmid": "PMID",
    "date": "Date (full)",
    _OTHER_IDS: "Other ID",
}


_FIELD_ORDER = (
    "doi",
    "pmid",
    "title",
    "authors",
    "keywords",
    "abstract",
    "publisher",
    "journal",
    "conference_name",
    "publication_type",
    "date",
    "year",
    "month",
    "day",
    ISSN_ISBN_TARGET,
    "issn",
    "isbn",
    "volume",
    "issue",
    "pages",
    "page_start",
    "page_end",
    "language",
    "url",
    _OTHER_IDS,
    "notes",
)

Status = Literal["green", "orange", "red"]
_STATUS_ORDER: tuple[Status, ...] = ("green", "orange", "red")
_CHANGED = "blue"
_STATUS_COLORS = {
    "green": "green-2",
    "orange": "orange-2",
    "red": "red-2",
    _CHANGED: "blue-2",
}


def _initial_status(header: str, suggestion: FieldMapping) -> Status:
    target = suggestion.targets.get(header)
    if target is None:
        return "red"
    shared = sum(t == target for t in suggestion.targets.values()) > 1
    if shared or suggestion.match_kinds.get(header) != "exact":
        return "orange"
    return "green"


def _sorted_headers(headers: list[str], suggestion: FieldMapping) -> list[str]:
    def sort_key(header: str) -> tuple[int, int]:
        status = _initial_status(header, suggestion)
        target = suggestion.targets.get(header, "")
        if target.startswith(OTHER_IDS_PREFIX):
            target = _OTHER_IDS
        position = _FIELD_ORDER.index(target) if status != "red" else 0
        return _STATUS_ORDER.index(status), position

    return sorted(headers, key=sort_key)


def _option_label(key: str) -> str:
    return _LABELS.get(key, key.replace("_", " ").capitalize())


_INPUT_WIDTH_CH = (8, 24)
_SELECT_CHROME_CH = 6


def _sorted_options(keys: Iterable[str]) -> dict[str, str]:
    options = {key: _option_label(key) for key in keys}
    return dict(sorted(options.items(), key=lambda item: item[1].lower()))


def _input_width_ch(headers: list[str]) -> int:
    low, high = _INPUT_WIDTH_CH
    return max(low, min(high, max(map(len, headers), default=0) + 1))


def _mapping_width_ch() -> int:
    return max(len(_option_label(key)) for key in _ALL_TARGET_KEYS) + _SELECT_CHROME_CH


def _exclusive_available(header: str, target: str, taken: dict[str, str]) -> bool:
    return taken.get(target) in (None, header)


_LIST_SEPARATOR = " | "
_NOT_PARSED = "not parsed"
_RESULT_CLASSES = "w-48 truncate text-xs"
_RESULT_TEXT_COLORS = {"green": "text-positive", "red": "text-negative"}


def _fill_color(filled: int, total: int) -> str:
    if 3 * filled >= 2 * total and total:
        return "green"
    if 3 * filled >= total and total:
        return "orange"
    return "red"


def _result_status(text: str, sample: str, not_parsed: bool) -> Status | None:
    if not_parsed:
        return "red"
    if not text or text == sample:
        return None
    return "green"


def _author_text(author: Author) -> str:
    details = [f"ORCID {author.orcid}"] if author.orcid else []
    details += [
        affiliation.name for affiliation in author.affiliations if affiliation.name
    ]
    name = author.full_name or ""
    return f"{name} ({'; '.join(details)})" if details else name


def _date_text(date: PartialDate | None) -> str:
    if date is None:
        return ""
    parts = [
        str(date.year) if date.year is not None else "",
        f"{date.month:02}" if date.month is not None else "",
        f"{date.day:02}" if date.day is not None else "",
    ]
    return "-".join(part for part in parts if part)


def _result_text(target: str, record: Record) -> str:
    if target in DATE_TARGETS:
        return _date_text(record.publication_date)
    if target in PAGE_TARGETS:
        return record.pages or ""
    if target == ISSN_ISBN_TARGET:
        ids = (("ISSN", record.issn), ("ISBN", record.isbn))
        return _LIST_SEPARATOR.join(f"{label} {value}" for label, value in ids if value)
    if target.startswith(OTHER_IDS_PREFIX):
        return record.other_ids.get(target.removeprefix(OTHER_IDS_PREFIX), "")
    if target == "authors":
        return _LIST_SEPARATOR.join(map(_author_text, record.authors))
    if target == "keywords":
        return _LIST_SEPARATOR.join(record.keywords)
    value: str | None = getattr(record, target)
    return value or ""


@dataclass
class _Row:
    header: str
    sample: ui.label
    result: ui.label
    count: ui.linear_progress
    select: ui.select
    other_id_key: str
    status: Status
    initial_target: str

    @property
    def display_status(self) -> str:
        return _CHANGED if self.select.value != self.initial_target else self.status


@dataclass
class MappingScreen:
    preview: Callable[[FieldMapping], Record]
    rows: list[_Row] = field(default_factory=list)
    list_delimiter: str = ";"
    list_delimiter_input: ui.input | None = None

    def _row_for(self, header: str) -> _Row:
        return next(row for row in self.rows if row.header == header)

    def _refresh_options(self) -> None:
        taken: dict[str, str] = {}
        for row in self.rows:
            if row.select.value in EXCLUSIVE_TARGETS:
                taken[row.select.value] = row.header

        for row in self.rows:
            keys = list(_BASE_TARGET_KEYS) + [
                target
                for target in EXCLUSIVE_TARGETS
                if _exclusive_available(row.header, target, taken)
            ]
            row.select.set_options(_sorted_options(keys))

    def _refresh_colors(self) -> None:
        for row in self.rows:
            row.select.props(f"bg-color={_STATUS_COLORS[row.display_status]}")

    def _refresh_results(self) -> None:
        mapping = self.current_mapping()
        record = self.preview(mapping)
        for row in self.rows:
            target = mapping.targets.get(row.header)
            text = _result_text(target, record) if target else ""
            not_parsed = bool(target and row.sample.text and not text)
            row.result.set_text(_NOT_PARSED if not_parsed else text)
            status = _result_status(text, row.sample.text, not_parsed)
            color = _RESULT_TEXT_COLORS[status] if status else "text-grey-7"
            row.result.classes(replace=f"{_RESULT_CLASSES} {color}")
            row.result.clear()
            if text:
                with row.result:
                    ui.tooltip(text)

    def on_target_change(self) -> None:
        self._refresh_options()
        self._refresh_colors()
        self._refresh_results()

    def set_target(self, header: str, target: str) -> None:
        row = self._row_for(header)
        row.select.value = target
        self._refresh_options()

    def available_targets(self, header: str) -> set[str]:
        return set(self._row_for(header).select.options)

    def current_mapping(self) -> FieldMapping:
        targets: dict[str, str] = {}
        for row in self.rows:
            target = row.select.value
            if target == _IGNORE:
                continue
            if target == _OTHER_IDS:
                target = OTHER_IDS_PREFIX + row.other_id_key
            targets[row.header] = target

        delimiter = (
            self.list_delimiter_input.value
            if self.list_delimiter_input
            else self.list_delimiter
        )
        return FieldMapping(targets=targets, list_delimiter=delimiter or ";")


def render_mapping_table(
    middle: Element,
    summary: FileSummary,
    suggestion: FieldMapping,
    *,
    show_delimiter: bool,
    preview: Callable[[FieldMapping], Record],
    chosen: FieldMapping | None = None,
) -> MappingScreen:
    delimiter = (chosen or suggestion).list_delimiter
    screen = MappingScreen(preview=preview, list_delimiter=delimiter)
    samples = summary.samples
    headers = _sorted_headers(list(samples), suggestion)
    input_width = _input_width_ch(headers)
    input_style = f"width: {input_width}ch"
    mapping_style = f"width: {_mapping_width_ch()}ch"

    suggested = suggestion.targets
    initial_targets: dict[str, str] = {}
    initial_keys: dict[str, str] = {}
    for header in headers:
        target = suggested.get(header, _IGNORE)
        initial_keys[header] = default_other_id_key(header)
        if target.startswith(OTHER_IDS_PREFIX):
            initial_keys[header] = target.removeprefix(OTHER_IDS_PREFIX)
            target = _OTHER_IDS
        initial_targets[header] = target

    ui.add_css(_ROW_FIELD_CSS)

    count_cell_classes = "self-stretch flex items-center px-2 mr-1"
    count_cell_style = "background: rgba(0, 0, 0, 0.04)"

    middle.clear()
    with middle:
        table_classes = "gap-0 border rounded-borders max-w-full overflow-x-auto"
        with ui.column().classes(table_classes):
            row_base = "w-full min-w-max no-wrap items-center gap-1 pl-0 border-b"
            with ui.row().classes(f"{row_base} py-2 bg-grey-2"):
                with (
                    ui.element("div")
                    .classes(count_cell_classes)
                    .style(count_cell_style)
                ):
                    ui.label("#").classes("w-10 text-xs font-bold text-center")
                ui.label("Input").classes("text-xs font-bold").style(input_style)
                ui.label("Mapping").classes("text-xs font-bold").style(mapping_style)
                ui.label("Example").classes("w-48 text-xs font-bold text-center")
                ui.label("Result").classes("w-48 text-xs font-bold text-center")
            for i, header in enumerate(headers):
                status = _initial_status(header, suggestion)
                row_classes = f"{row_base} py-0"
                if i % 2 == 1:
                    row_classes += " bg-grey-1"
                with ui.row().classes(row_classes):
                    filled = summary.filled.get(header, 0)
                    ratio = filled / summary.total_rows if summary.total_rows else 0.0
                    with (
                        ui.element("div")
                        .classes(count_cell_classes)
                        .style(count_cell_style)
                    ):
                        count = ui.linear_progress(value=ratio, show_value=False)
                        count.props(f"color={_fill_color(filled, summary.total_rows)}")
                        count.classes("w-10")
                        count.tooltip(f"{filled} of {summary.total_rows}")
                    label = ui.label(header).classes("truncate text-xs")
                    label.style(input_style)
                    if len(header) >= input_width:
                        label.tooltip(header)
                    select = (
                        ui.select(
                            _sorted_options(_ALL_TARGET_KEYS),
                            value=initial_targets[header],
                        )
                        .classes("mapping-field text-xs")
                        .style(mapping_style)
                        .props(
                            "dense options-dense outlined "
                            f"bg-color={_STATUS_COLORS[status]}"
                        )
                    )
                    sample = ui.label(samples[header]).classes(
                        "w-48 truncate text-xs text-grey-7"
                    )
                    if samples[header]:
                        sample.tooltip(samples[header])
                    result = ui.label().classes(_RESULT_CLASSES)

                screen.rows.append(
                    _Row(
                        header=header,
                        sample=sample,
                        result=result,
                        count=count,
                        select=select,
                        other_id_key=initial_keys[header],
                        status=status,
                        initial_target=initial_targets[header],
                    )
                )
                select.on_value_change(lambda _e: screen.on_target_change())

        if show_delimiter:
            screen.list_delimiter_input = (
                ui.input("List delimiter", value=delimiter)
                .classes("pl-6 text-xs")
                .props("dense")
            )
            screen.list_delimiter_input.on_value_change(
                lambda _e: screen._refresh_results()
            )

    if chosen is not None:
        for row in screen.rows:
            target = chosen.targets.get(row.header, _IGNORE)
            if target.startswith(OTHER_IDS_PREFIX):
                target = _OTHER_IDS
            row.select.value = target
            row.select.props("readonly")
        if screen.list_delimiter_input is not None:
            screen.list_delimiter_input.props("readonly")

    screen._refresh_options()
    screen._refresh_results()
    return screen
