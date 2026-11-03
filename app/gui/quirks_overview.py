from dataclasses import dataclass, field

from nicegui import ui
from nicegui.element import Element

from app.parsers.profiles.overview import (
    Kind,
    Origin,
    QuirkChoice,
    QuirkChoices,
    QuirkEntry,
    QuirkOption,
)

_KIND_ORDER: tuple[Kind, ...] = ("toggleable", "setting", "parser")
_ORIGIN_ORDER: tuple[Origin, ...] = ("general", "type")
_CHANGED_BG_COLOR = "blue-2"
_CHANGED_CHECKBOX_COLOR = "blue"
# Dense boxes no taller than a line of text-sm (20px).
_FIELD_CSS = """
.quirk-field .q-field__control, .quirk-field .q-field__marginal {
    min-height: 20px;
    height: 20px;
    align-items: center;
}
.quirk-field .q-field__control-container {
    padding-top: 0;
    align-items: center;
}
.quirk-field .q-field__native, .quirk-field .q-field__input {
    padding: 0;
    min-height: 0;
}
"""
_CHECKBOX_SIZE = "32px"
_OPTION_LABEL_CLASSES = "shrink-0 text-xs text-grey-7"
_TOOLTIP_CLASSES = "max-w-sm text-xs whitespace-pre-line"
_NEW_LINE = "\n"
_NEW_LINE_ESCAPE = "\\n"


def _escape(value: str) -> str:
    return value.replace(_NEW_LINE, _NEW_LINE_ESCAPE)


def _unescape(value: str) -> str:
    return value.replace(_NEW_LINE_ESCAPE, _NEW_LINE)


@dataclass
class _EntryWidgets:
    entry: QuirkEntry
    checkbox: ui.checkbox | None
    inputs: dict[str, ui.select | ui.input | ui.number] = field(default_factory=dict)


def _option_value(
    option: QuirkOption, widget: ui.select | ui.input | ui.number, default: str
) -> str:
    """An empty box means the default, as in the mapping options."""
    value = widget.value
    if option.numeric:
        return str(int(value)) if value else default
    if option.choices is not None:
        return str(value)
    text = _unescape(value.strip() if option.strip else value)
    return text or default


@dataclass
class QuirksScreen:
    readonly: bool
    entries: list[_EntryWidgets] = field(default_factory=list)

    def _choice(self, widgets: _EntryWidgets) -> QuirkChoice:
        default = widgets.entry.default
        values = {
            option.name: _option_value(
                option, widgets.inputs[option.name], default.values[option.name]
            )
            for option in widgets.entry.options
        }
        on = widgets.checkbox.value if widgets.checkbox else default.on
        return QuirkChoice(on=on, values=values)

    def current_choices(self) -> QuirkChoices:
        return {widgets.entry.key: self._choice(widgets) for widgets in self.entries}

    def _refresh_colors(self, widgets: _EntryWidgets) -> None:
        choice = self._choice(widgets)
        default = widgets.entry.default
        if widgets.checkbox is not None:
            if choice.on != default.on:
                widgets.checkbox.props(f"color={_CHANGED_CHECKBOX_COLOR}")
            else:
                widgets.checkbox.props(remove="color")
        # Text boxes show their default as placeholder, so only dropdowns get tinted.
        for name, widget in widgets.inputs.items():
            if not isinstance(widget, ui.select):
                continue
            if choice.values[name] != default.values[name]:
                widget.props(f"bg-color={_CHANGED_BG_COLOR}")
            else:
                widget.props(remove="bg-color")

    def restore_defaults(self) -> None:
        for widgets in self.entries:
            default = widgets.entry.default
            if widgets.checkbox is not None:
                widgets.checkbox.value = default.on
            for option in widgets.entry.options:
                widget = widgets.inputs[option.name]
                if option.choices is not None:
                    widget.value = default.values[option.name]
                else:
                    widget.value = None if option.numeric else ""

    def set_on(self, key: str, on: bool) -> None:
        widgets = self._widgets_for(key)
        assert widgets.checkbox is not None
        widgets.checkbox.value = on

    def set_option(self, key: str, name: str, value: str) -> None:
        self._widgets_for(key).inputs[name].value = value

    def _widgets_for(self, key: str) -> _EntryWidgets:
        return next(w for w in self.entries if w.entry.key == key)

    def _render_option(
        self, widgets: _EntryWidgets, option: QuirkOption, value: str
    ) -> None:
        widget: ui.select | ui.input | ui.number
        with ui.row().classes("no-wrap items-center gap-1"):
            ui.label(option.label).classes(_OPTION_LABEL_CLASSES)
            if option.choices is not None:
                widget = ui.select(option.choices, value=value)
                widget.props("dense options-dense outlined")
            elif option.numeric:
                number = float(value)
                widget = ui.number(
                    value=number if self.readonly else None,
                    placeholder=value,
                    min=1,
                    precision=0,
                ).props("dense outlined")
            elif self.readonly:
                widget = ui.input(value=_escape(value)).props("dense outlined")
            else:
                widget = ui.input(placeholder=_escape(value)).props("dense outlined")
            if self.readonly:
                widget.props("readonly")
            widget.classes("quirk-field text-xs w-32")
            widget.on_value_change(lambda _e: self._refresh_colors(widgets))
        widgets.inputs[option.name] = widget

    def _render_entry(self, entry: QuirkEntry, choice: QuirkChoice) -> None:
        hover = [entry.explanation]
        if entry.used_by:
            hover.append(f"Used by: {', '.join(entry.used_by)}.")
        hover += entry.details
        with ui.row().classes("items-center no-wrap gap-3 w-full"):
            title: ui.checkbox | ui.label
            checkbox = None
            if entry.kind == "toggleable":
                title = checkbox = ui.checkbox(entry.title, value=choice.on)
                checkbox.props(f"dense keep-color size={_CHECKBOX_SIZE}")
                if self.readonly:
                    checkbox.props("disable")
            else:
                title = ui.label(entry.title)
            title.classes("text-sm")
            with title:
                ui.tooltip(_NEW_LINE.join(hover)).classes(_TOOLTIP_CLASSES)
            widgets = _EntryWidgets(entry=entry, checkbox=checkbox)
            for option in entry.options:
                self._render_option(widgets, option, choice.values[option.name])
        if checkbox is not None:
            checkbox.on_value_change(lambda _e: self._refresh_colors(widgets))
        self.entries.append(widgets)
        self._refresh_colors(widgets)


def render_quirks_overview(
    container: Element,
    entries: list[QuirkEntry],
    type_label: str,
    chosen: QuirkChoices | None = None,
) -> QuirksScreen:
    """`chosen` shows a stored import's choices read-only."""
    screen = QuirksScreen(readonly=chosen is not None)
    origin_labels: dict[Origin, str] = {"general": "General", "type": type_label}
    blocks = [
        (origin, [e for e in entries if e.origin == origin]) for origin in _ORIGIN_ORDER
    ]
    ui.add_css(_FIELD_CSS)
    container.clear()
    with container, ui.column().classes("gap-1 w-full max-w-2xl"):
        for i, (origin, block) in enumerate(b for b in blocks if b[1]):
            if i:
                ui.separator().classes("my-2")
            ui.label(origin_labels[origin]).classes("text-base font-bold")
            for entry in sorted(block, key=lambda e: _KIND_ORDER.index(e.kind)):
                choice = (chosen or {}).get(entry.key, entry.default)
                screen._render_entry(entry, choice)
        if not screen.readonly:
            with ui.row().classes("w-full justify-end"):
                ui.button("Restore defaults", on_click=screen.restore_defaults).props(
                    "dense flat no-caps"
                )
    return screen
