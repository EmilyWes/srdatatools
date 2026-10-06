from dataclasses import dataclass, field

from nicegui import ui
from nicegui.element import Element

from app.parsers.mapping import (
    EXCLUSIVE_TARGETS,
    LIST_TARGETS,
    OTHER_IDS_PREFIX,
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

_BASE_TARGET_KEYS = (_IGNORE, *sorted(SCALAR_FIELDS), *LIST_TARGETS, _OTHER_IDS)
_ALL_TARGET_KEYS = (*_BASE_TARGET_KEYS, *EXCLUSIVE_TARGETS)

_LABELS: dict[str, str] = {
    "doi": "DOI",
    "issn": "ISSN",
    "isbn": "ISBN",
    "pmid": "PMID",
    "date": "Date (full)",
    _OTHER_IDS: "Other ID",
}


def _option_label(key: str) -> str:
    return _LABELS.get(key, key.replace("_", " ").capitalize())


def _exclusive_available(header: str, target: str, taken: dict[str, str]) -> bool:
    return taken.get(target) in (None, header)


@dataclass
class _Row:
    header: str
    sample: ui.label
    select: ui.select
    other_id_key: str


@dataclass
class MappingScreen:
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
            row.select.set_options({key: _option_label(key) for key in keys})

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
    samples: dict[str, str],
    suggestion: FieldMapping,
    *,
    show_delimiter: bool,
) -> MappingScreen:
    screen = MappingScreen(list_delimiter=suggestion.list_delimiter)
    headers = list(samples)

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

    middle.clear()
    with middle:
        with ui.column().classes("gap-0 border rounded-borders"):
            header_classes = "w-full items-center gap-1 pl-6 py-2 bg-grey-2 border-b"
            with ui.row().classes(header_classes):
                ui.label("Input").classes("w-48 text-xs font-bold")
                ui.label("Mapping").classes("w-40 text-xs font-bold")
                ui.label("Example").classes("w-48 text-xs font-bold")
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
                        .classes("mapping-field w-40 text-xs")
                        .props("dense options-dense outlined")
                    )
                    sample = ui.label(samples[header]).classes(
                        "w-48 truncate text-xs text-grey-7"
                    )
                    if samples[header]:
                        sample.tooltip(samples[header])

                screen.rows.append(
                    _Row(
                        header=header,
                        sample=sample,
                        select=select,
                        other_id_key=initial_keys[header],
                    )
                )
                select.on_value_change(lambda _e: screen._refresh_options())

        if show_delimiter:
            screen.list_delimiter_input = (
                ui.input("List delimiter", value=suggestion.list_delimiter)
                .classes("pl-6 text-xs")
                .props("dense")
            )

    screen._refresh_options()
    return screen
