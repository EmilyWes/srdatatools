from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from nicegui import ui
from nicegui.element import Element

from app.gui.importing.common import FileSummary
from app.gui.importing.mapping import (
    AUTHORS_TARGET,
    DATE_TARGET,
    ISSN_ISBN_TARGET,
    KEYWORDS_TARGET,
    LABEL_TARGET,
    OTHER_IDS_TARGET,
    PAGES_TARGET,
    TARGETS,
    AuthorsRow,
    DateRow,
    FieldMapping,
    IssnIsbnRow,
    KeywordsRow,
    LabelRow,
    OtherIdRow,
    PagesRow,
    RowMapping,
    default_row,
    row_with,
)
from app.helpers.record_fields import DATE_PART_LABELS, FIELD_LABELS
from app.helpers.theme import (
    CHANGED_TINT,
    FIELD_CLASSES,
    INPUT_PROPS,
    MUTED_TEXT,
    OUTLINED_BOX,
    SELECT_PROPS,
    STATUS_TINTS,
)

_IGNORE = "ignore"
_TARGET_KEYS = (_IGNORE, *TARGETS)

# Targets that aren't a Record field of the same name; "Other ID" is singular
# since one column gives one ID.
_TARGET_LABELS: dict[str, str] = {
    ISSN_ISBN_TARGET: "ISSN/ISBN",
    DATE_TARGET: FIELD_LABELS["publication_date"],
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


_OPTION_ROW_CLASSES = "w-full no-wrap items-center gap-1"
# Fixed width so the boxes line up whatever the label.
_OPTION_LABEL_CLASSES = f"w-10 shrink-0 text-xs {MUTED_TEXT}"

_OPTIONS: dict[str, tuple[_Option, ...]] = {
    DATE_TARGET: (_Option("part", "part", "Part", DATE_PART_LABELS),),
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
                "names": "Names",
                "ids": "Author IDs",
                "affiliations": "Affiliations",
            },
        ),
        _Option("id_key", "key", "ID key"),
    ),
    KEYWORDS_TARGET: (_Option("prefix", "pre", "Prefix"),),
    LABEL_TARGET: (
        _Option("phase", "phase", "Phase"),
        _Option("screener", "scr", "Screener"),
    ),
}


def _shows_option(row: RowMapping, name: str) -> bool:
    if isinstance(row, AuthorsRow) and name == "id_key":
        return row.role == "ids"
    return True


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
_STATUS_COLORS = {**STATUS_TINTS, _CHANGED: CHANGED_TINT}


def _value_slot(row: RowMapping) -> tuple[str, ...] | None:
    """Where the row's value goes; None for rows whose values are all kept."""
    if isinstance(row, KeywordsRow) or (
        isinstance(row, AuthorsRow) and row.role == "ids"
    ):
        return None
    if isinstance(row, DateRow | PagesRow):
        return row.target, row.part
    if isinstance(row, AuthorsRow):
        return row.target, row.role
    if isinstance(row, OtherIdRow):
        return row.target, row.key
    if isinstance(row, LabelRow):
        return row.target, row.phase, row.screener
    return (row.target,)


def _clashes(a: RowMapping, b: RowMapping) -> bool:
    """Whether two rows compete for one value, so only the first filled one wins."""
    if isinstance(a, IssnIsbnRow) and isinstance(b, IssnIsbnRow):
        return a.kind == b.kind or "auto" in (a.kind, b.kind)
    slot = _value_slot(a)
    return slot is not None and slot == _value_slot(b)


def _initial_status(header: str, suggestion: FieldMapping) -> Status:
    row = suggestion.rows.get(header)
    if row is None:
        return "red"
    shared = any(
        _clashes(row, other) for key, other in suggestion.rows.items() if key != header
    )
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
    if key in _TARGET_LABELS:
        return _TARGET_LABELS[key]
    return FIELD_LABELS.get(key, key.replace("_", " ").capitalize())


_INPUT_WIDTH_CH = (8, 24)
SELECT_CHROME_CH = 6


def sorted_target_options(keys: Iterable[str]) -> dict[str, str]:
    options = {key: _option_label(key) for key in keys}
    return dict(sorted(options.items(), key=lambda item: item[1].lower()))


def input_width_ch(texts: Iterable[str], chrome: int = 1) -> int:
    low, high = _INPUT_WIDTH_CH
    return max(low, min(high, max(map(len, texts), default=0) + chrome))


def _mapping_width_ch() -> int:
    return max(len(_option_label(key)) for key in _TARGET_KEYS) + SELECT_CHROME_CH


# Without overflow-y-hidden, overflow-x-auto turns on vertical scrolling too.
_TABLE_CLASSES = f"gap-0 {OUTLINED_BOX} max-w-full overflow-x-auto overflow-y-hidden"
_ROW_CLASSES = (
    "w-full min-w-max no-wrap items-center gap-1 pl-0 border-b outline-variant"
)
_COUNT_CELL_CLASSES = "self-stretch flex items-center px-2 mr-1"
_COUNT_CELL_STYLE = "background: rgba(0, 0, 0, 0.04)"
_HEADER_LABEL_CLASSES = "text-xs font-bold"
_EXAMPLE_WIDTH = "w-48"


def _width(width_ch: int) -> str:
    return f"w-[{width_ch}ch]"


def table_frame() -> ui.column:
    return ui.column().classes(_TABLE_CLASSES)


def header_row() -> ui.row:
    return ui.row().classes(f"{_ROW_CLASSES} py-2 surface-container")


def body_row(index: int) -> ui.row:
    striped = " surface-low" if index % 2 == 1 else ""
    return ui.row().classes(f"{_ROW_CLASSES} py-0{striped}")


def header_cells(
    label_title: str, widget_title: str, label_ch: int, widget_ch: int
) -> None:
    with ui.element("div").classes(_COUNT_CELL_CLASSES).style(_COUNT_CELL_STYLE):
        ui.label("#").classes(f"w-10 {_HEADER_LABEL_CLASSES} text-center")
    ui.label(label_title).classes(f"{_HEADER_LABEL_CLASSES} {_width(label_ch)}")
    ui.label(widget_title).classes(f"{_HEADER_LABEL_CLASSES} {_width(widget_ch)}")
    ui.label("Example").classes(f"{_EXAMPLE_WIDTH} {_HEADER_LABEL_CLASSES} text-center")


def count_cell() -> tuple[Element, ui.linear_progress]:
    with (
        ui.element("div").classes(_COUNT_CELL_CLASSES).style(_COUNT_CELL_STYLE) as cell
    ):
        count = ui.linear_progress(show_value=False).classes("w-10")
    return cell, count


def label_cell(text: str, width_ch: int) -> ui.label:
    label = ui.label(text).classes(f"truncate text-xs {_width(width_ch)}")
    if len(text) >= width_ch:
        label.tooltip(text)
    return label


def widget_cell(width_ch: int) -> ui.column:
    return ui.column().classes(f"gap-0 {_width(width_ch)}")


def example_cell(text: str) -> ui.label:
    sample = ui.label(text).classes(f"{_EXAMPLE_WIDTH} truncate text-xs {MUTED_TEXT}")
    if text:
        sample.tooltip(text)
    return sample


def option_row(short: str, label: str) -> ui.row:
    with ui.row().classes(_OPTION_ROW_CLASSES) as row:
        ui.label(f"{short}:").classes(_OPTION_LABEL_CLASSES).tooltip(label)
    return row


def fill_color(filled: int, total: int) -> str:
    if 3 * filled >= 2 * total and total:
        return "green"
    if 3 * filled >= total and total:
        return "orange"
    return "red"


@dataclass
class _Row:
    header: str
    sample: ui.label
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
            row.base = default_row(target, row.header)
        row.inputs = {}
        row.options.clear()
        base = row.base.model_dump() if row.base is not None else {}
        row.option_rows = {}
        for option in _OPTIONS.get(target, ()):
            with row.options, option_row(option.short, option.label) as shown_row:
                widget: ui.select | ui.input
                if option.choices is not None:
                    widget = ui.select(option.choices, value=base[option.name])
                    widget.props(SELECT_PROPS)
                elif self.readonly:
                    widget = ui.input(value=base[option.name]).props(INPUT_PROPS)
                else:
                    widget = ui.input(placeholder=base[option.name])
                    widget.props(INPUT_PROPS)
                if self.readonly:
                    widget.props("readonly")
                widget.classes(f"{FIELD_CLASSES} col")
                widget.on_value_change(lambda _e: self.on_option_change(row))
            row.inputs[option.name] = widget
            row.option_rows[option.name] = shown_row
        self._refresh_option_visibility(row)
        self._refresh_option_colors(row)

    def _refresh_option_visibility(self, row: _Row) -> None:
        mapped = self._row_mapping(row)
        for name, option_row in row.option_rows.items():
            shown = mapped is not None and _shows_option(mapped, name)
            option_row.set_visibility(shown)

    def _refresh_option_colors(self, row: _Row) -> None:
        mapped = self._row_mapping(row)
        if mapped is None:
            return
        assert row.base is not None
        for name, widget in row.inputs.items():
            changed = getattr(mapped, name) != getattr(row.base, name)
            status = _CHANGED if changed else "green"
            widget.props(f"bg-color={_STATUS_COLORS[status]}")

    def on_target_change(self, row: _Row) -> None:
        self._build_options(row)
        self._refresh_colors()

    def on_option_change(self, row: _Row) -> None:
        self._refresh_option_visibility(row)
        self._refresh_option_colors(row)

    def set_target(self, header: str, target: str) -> None:
        self._row_for(header).select.value = target

    def set_option(self, header: str, name: str, value: str) -> None:
        self._row_for(header).inputs[name].value = value

    def _row_mapping(self, row: _Row) -> RowMapping | None:
        if row.base is None:
            return None
        options = {
            option.name: row.inputs[option.name].value.strip()
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


def render_mapping_table(
    middle: Element,
    summary: FileSummary,
    suggestion: FieldMapping,
    *,
    chosen: FieldMapping | None = None,
) -> MappingScreen:
    screen = MappingScreen(readonly=chosen is not None)
    samples = summary.samples
    headers = _sorted_headers(list(samples), suggestion)
    input_width = input_width_ch(headers)
    mapping_width = _mapping_width_ch()

    initial_targets = {
        header: (
            suggested.target if (suggested := suggestion.rows.get(header)) else _IGNORE
        )
        for header in headers
    }

    middle.clear()
    with middle:
        with table_frame():
            with header_row():
                header_cells("Input", "Mapping", input_width, mapping_width)
            for i, header in enumerate(headers):
                status = _initial_status(header, suggestion)
                with body_row(i):
                    filled = summary.filled.get(header, 0)
                    _, count = count_cell()
                    count.value = (
                        filled / summary.total_rows if summary.total_rows else 0.0
                    )
                    count.props(f"color={fill_color(filled, summary.total_rows)}")
                    count.tooltip(f"{filled} of {summary.total_rows}")
                    label_cell(header, input_width)
                    with widget_cell(mapping_width):
                        select = (
                            ui.select(
                                sorted_target_options(_TARGET_KEYS),
                                value=initial_targets[header],
                            )
                            .classes(f"{FIELD_CLASSES} w-full")
                            .props(f"{SELECT_PROPS} bg-color={_STATUS_COLORS[status]}")
                        )
                        options = ui.column().classes("gap-0 w-full")
                    sample = example_cell(samples[header])

                mapped = (chosen or suggestion).rows.get(header)
                if chosen is not None:
                    select.value = mapped.target if mapped is not None else _IGNORE
                    select.props("readonly")
                row = _Row(
                    header=header,
                    sample=sample,
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
    return screen
