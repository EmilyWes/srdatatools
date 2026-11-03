from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from nicegui import ui
from nicegui.element import Element

from app.models.record import Author, PartialDate, Record
from app.parsers.common import FileSummary
from app.parsers.mapping import (
    AUTHORS_TARGET,
    DATE_TARGET,
    ISSN_ISBN_TARGET,
    KEYWORDS_TARGET,
    LABEL_TARGET,
    LINE_DELIMITER,
    OTHER_IDS_TARGET,
    PAGES_TARGET,
    TARGETS,
    AuthorsRow,
    DateRow,
    FieldMapping,
    IssnIsbnRow,
    LabelRow,
    OtherIdRow,
    PagesRow,
    RowDefaults,
    RowMapping,
    default_row,
    is_ambiguous_date,
    row_with,
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
_TARGET_KEYS = (_IGNORE, *TARGETS)

_LABELS: dict[str, str] = {
    "doi": "DOI",
    ISSN_ISBN_TARGET: "ISSN/ISBN",
    "pmid": "PMID",
    "date": "Publication date",
    OTHER_IDS_TARGET: "Other ID",
}


@dataclass(frozen=True)
class _Option:
    """An option shown under the dropdown: a select when it has choices, else a
    text box whose grey placeholder is the default used when left empty. A short
    label goes in front of it, with the full one on hover."""

    name: str
    short: str
    label: str
    choices: dict[str, str] | None = None
    # Delimiters and separators may be or end in a space.
    strip: bool = True


_OPTION_ROW_CLASSES = "w-full no-wrap items-center gap-1"
# Fixed width so the boxes line up whatever the label.
_OPTION_LABEL_CLASSES = "w-10 shrink-0 text-xs text-grey-7"

_OPTIONS: dict[str, tuple[_Option, ...]] = {
    DATE_TARGET: (
        _Option(
            "part",
            "part",
            "Part",
            {"full": "Full date", "year": "Year", "month": "Month", "day": "Day"},
        ),
        _Option(
            "order",
            "order",
            "Ambiguous dates",
            {"eu": "Day before month (EU)", "us": "Month before day (US)"},
        ),
    ),
    PAGES_TARGET: (
        _Option(
            "part",
            "part",
            "Part",
            {
                "range": "Range",
                "start": "Start page",
                "end": "End page",
                "count": "Number of pages",
            },
        ),
    ),
    ISSN_ISBN_TARGET: (
        _Option(
            "kind",
            "kind",
            "Kind",
            {"auto": "Auto (by length)", "issn": "ISSN", "isbn": "ISBN"},
        ),
    ),
    OTHER_IDS_TARGET: (_Option("key", "key", "ID key"),),
    AUTHORS_TARGET: (
        _Option(
            "role",
            "role",
            "Role",
            {
                "full_name": "Full name (not split)",
                "first_last": "Names: first, last",
                "last_first": "Names: last, first",
                "orcid": "ORCID",
                "ids": "Author IDs",
                "affiliations": "Affiliations",
            },
        ),
        _Option("delimiter", "aut", "Author separator", strip=False),
        _Option("separator", "name", "Name separator", strip=False),
        _Option("id_key", "key", "ID key"),
    ),
    KEYWORDS_TARGET: (
        _Option("delimiter", "sep", "Delimiter", strip=False),
        _Option("prefix", "pre", "Prefix"),
    ),
    LABEL_TARGET: (
        _Option("phase", "phase", "Phase"),
        _Option("screener", "scr", "Screener"),
    ),
}


def _shows_option(row: RowMapping, name: str) -> bool:
    if isinstance(row, DateRow) and name == "order":
        return row.part == "full"
    if isinstance(row, AuthorsRow) and name == "separator":
        return row.role in ("first_last", "last_first")
    if isinstance(row, AuthorsRow) and name == "id_key":
        return row.role == "ids"
    if name == "delimiter":
        delimiter: str = getattr(row, name)
        return delimiter != LINE_DELIMITER
    return True


def _needs_a_look(row: RowMapping, name: str, sample: str) -> bool:
    if not sample:
        return False
    if name == "delimiter":
        delimiter: str = getattr(row, name)
        return delimiter not in sample
    if isinstance(row, AuthorsRow) and name == "separator":
        names = sample.split(row.delimiter)
        return not any(row.separator in author for author in names)
    if isinstance(row, DateRow) and name == "order":
        return is_ambiguous_date(sample)
    return False


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
    ISSN_ISBN_TARGET,
    "volume",
    "issue",
    "pages",
    "language",
    "url",
    OTHER_IDS_TARGET,
    LABEL_TARGET,
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
    row = suggestion.rows.get(header)
    if row is None:
        return "red"
    shared = sum(r.target == row.target for r in suggestion.rows.values()) > 1
    if shared or suggestion.match_kinds.get(header) != "exact":
        return "orange"
    return "green"


def _sorted_headers(headers: list[str], suggestion: FieldMapping) -> list[str]:
    def sort_key(header: str) -> tuple[int, int]:
        status = _initial_status(header, suggestion)
        row = suggestion.rows.get(header)
        position = _FIELD_ORDER.index(row.target) if row is not None else 0
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
    return max(len(_option_label(key)) for key in _TARGET_KEYS) + _SELECT_CHROME_CH


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
    details += [f"{key} {value}" for key, value in author.other_ids.items()]
    details += [
        affiliation.name for affiliation in author.affiliations if affiliation.name
    ]
    if author.family_name and author.given_name:
        name = f"{author.family_name}, {author.given_name}"
    else:
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


def _result_text(row: RowMapping, record: Record) -> str:
    if isinstance(row, DateRow):
        return _date_text(record.publication_date)
    if isinstance(row, PagesRow):
        return record.pages or ""
    if isinstance(row, IssnIsbnRow):
        ids = (("ISSN", record.issn), ("ISBN", record.isbn))
        return _LIST_SEPARATOR.join(f"{label} {value}" for label, value in ids if value)
    if isinstance(row, OtherIdRow):
        other_id = record.other_ids.get(row.key)
        return f"{row.key}: {other_id}" if other_id else ""
    if row.target == "authors":
        return _LIST_SEPARATOR.join(map(_author_text, record.authors))
    if row.target == "keywords":
        return _LIST_SEPARATOR.join(record.keywords)
    value: str | None = getattr(record, row.target)
    return value or ""


@dataclass
class _Row:
    header: str
    sample: ui.label
    result: ui.label
    count: ui.linear_progress
    select: ui.select
    options: ui.column
    mapped: RowMapping | None
    status: Status
    initial_target: str
    # The row the options start from: the suggested or chosen one while the
    # target is unchanged, else the target's default.
    base: RowMapping | None = None
    inputs: dict[str, ui.select | ui.input] = field(default_factory=dict)
    option_rows: dict[str, ui.row] = field(default_factory=dict)

    @property
    def display_status(self) -> str:
        return _CHANGED if self.select.value != self.initial_target else self.status


@dataclass
class MappingScreen:
    preview: Callable[[FieldMapping], Record]
    defaults: RowDefaults
    # Read-only text boxes show the stored value itself rather than a placeholder.
    readonly: bool = False
    rows: list[_Row] = field(default_factory=list)

    def _row_for(self, header: str) -> _Row:
        return next(row for row in self.rows if row.header == header)

    def _refresh_colors(self) -> None:
        for row in self.rows:
            row.select.props(f"bg-color={_STATUS_COLORS[row.display_status]}")

    def _build_options(self, row: _Row) -> None:
        target = row.select.value
        if target == _IGNORE:
            row.base = None
        elif row.mapped is not None and row.mapped.target == target:
            row.base = row.mapped
        else:
            row.base = default_row(target, row.header, self.defaults)
        row.inputs = {}
        row.options.clear()
        base = row.base.model_dump() if row.base is not None else {}
        row.option_rows = {}
        for option in _OPTIONS.get(target, ()):
            with row.options, ui.row().classes(_OPTION_ROW_CLASSES) as option_row:
                ui.label(f"{option.short}:").classes(_OPTION_LABEL_CLASSES).tooltip(
                    option.label
                )
                widget: ui.select | ui.input
                if option.choices is not None:
                    widget = ui.select(option.choices, value=base[option.name])
                    widget.props("dense options-dense outlined")
                elif self.readonly:
                    widget = ui.input(value=base[option.name]).props("dense outlined")
                else:
                    widget = ui.input(placeholder=base[option.name])
                    widget.props("dense outlined")
                if self.readonly:
                    widget.props("readonly")
                widget.classes("mapping-field text-xs col")
                widget.on_value_change(lambda _e: self.on_option_change(row))
            row.inputs[option.name] = widget
            row.option_rows[option.name] = option_row
        self._refresh_option_visibility(row)

    def _refresh_option_visibility(self, row: _Row) -> None:
        mapped = self._row_mapping(row)
        for name, option_row in row.option_rows.items():
            shown = mapped is not None and _shows_option(mapped, name)
            option_row.set_visibility(shown)

    def refresh_results(self) -> None:
        mapping = self.current_mapping()
        record = self.preview(mapping)
        label_headers = [key for key, _ in mapping.rows_of(LabelRow)]
        for row in self.rows:
            mapped = mapping.rows.get(row.header)
            target = mapped.target if mapped is not None else None
            text: str
            unknown_label = False
            if target == LABEL_TARGET:
                label = record.labels[label_headers.index(row.header)]
                text = f"{label.value} ({label.phase} / {label.screener})"
                unknown_label = label.value == "unknown"
            else:
                text = _result_text(mapped, record) if mapped is not None else ""
            not_parsed = bool(target and row.sample.text and not text)
            row.result.set_text(_NOT_PARSED if not_parsed else text)
            status = _result_status(text, row.sample.text, not_parsed)
            if unknown_label:
                status = "red"
            color = _RESULT_TEXT_COLORS[status] if status else "text-grey-7"
            row.result.classes(replace=f"{_RESULT_CLASSES} {color}")
            row.result.clear()
            if text:
                with row.result:
                    ui.tooltip(text)
            if mapped is not None:
                self._refresh_option_colors(row, mapped, failed=status == "red")

    def _refresh_option_colors(
        self, row: _Row, mapped: RowMapping, failed: bool
    ) -> None:
        assert row.base is not None
        for name, widget in row.inputs.items():
            status: str = "green"
            if getattr(mapped, name) != getattr(row.base, name):
                status = _CHANGED
            elif failed or _needs_a_look(mapped, name, row.sample.text):
                status = "orange"
            widget.props(f"bg-color={_STATUS_COLORS[status]}")

    def on_target_change(self, row: _Row) -> None:
        self._build_options(row)
        self._refresh_colors()
        self.refresh_results()

    def on_option_change(self, row: _Row) -> None:
        self._refresh_option_visibility(row)
        self.refresh_results()

    def set_target(self, header: str, target: str) -> None:
        self._row_for(header).select.value = target

    def set_option(self, header: str, name: str, value: str) -> None:
        self._row_for(header).inputs[name].value = value

    def _row_mapping(self, row: _Row) -> RowMapping | None:
        if row.base is None:
            return None
        options = {
            option.name: _option_value(option, row.inputs[option.name].value)
            for option in _OPTIONS.get(row.base.target, ())
            if option.name in row.inputs
        }
        defaults = row.base.model_dump()
        return row_with(row.base, {k: v or defaults[k] for k, v in options.items()})

    def current_mapping(self) -> FieldMapping:
        rows = {row.header: self._row_mapping(row) for row in self.rows}
        return FieldMapping(
            rows={header: row for header, row in rows.items() if row is not None}
        )


def _option_value(option: _Option, value: str) -> str:
    return value.strip() if option.strip else value


def render_mapping_table(
    middle: Element,
    summary: FileSummary,
    suggestion: FieldMapping,
    *,
    defaults: RowDefaults,
    preview: Callable[[FieldMapping], Record],
    chosen: FieldMapping | None = None,
) -> MappingScreen:
    screen = MappingScreen(
        preview=preview, defaults=defaults, readonly=chosen is not None
    )
    samples = summary.samples
    headers = _sorted_headers(list(samples), suggestion)
    input_width = _input_width_ch(headers)
    input_style = f"width: {input_width}ch"
    mapping_style = f"width: {_mapping_width_ch()}ch"

    initial_targets = {
        header: (
            suggested.target if (suggested := suggestion.rows.get(header)) else _IGNORE
        )
        for header in headers
    }

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
                    with ui.column().classes("gap-0").style(mapping_style):
                        select = (
                            ui.select(
                                _sorted_options(_TARGET_KEYS),
                                value=initial_targets[header],
                            )
                            .classes("mapping-field text-xs w-full")
                            .props(
                                "dense options-dense outlined "
                                f"bg-color={_STATUS_COLORS[status]}"
                            )
                        )
                        options = ui.column().classes("gap-0 w-full")
                    sample = ui.label(samples[header]).classes(
                        "w-48 truncate text-xs text-grey-7"
                    )
                    if samples[header]:
                        sample.tooltip(samples[header])
                    result = ui.label().classes(_RESULT_CLASSES)

                mapped = (chosen or suggestion).rows.get(header)
                if chosen is not None:
                    select.value = mapped.target if mapped is not None else _IGNORE
                    select.props("readonly")
                row = _Row(
                    header=header,
                    sample=sample,
                    result=result,
                    count=count,
                    select=select,
                    options=options,
                    mapped=mapped,
                    status=status,
                    initial_target=initial_targets[header],
                )
                screen.rows.append(row)
                screen._build_options(row)
                select.on_value_change(lambda _e, row=row: screen.on_target_change(row))

    screen._refresh_colors()
    screen.refresh_results()
    return screen
