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
_KIND_LABELS: dict[Kind, str] = {
    "toggleable": "on/off",
    "setting": "always on",
    "parser": "parser",
}
_ORIGIN_ORDER: tuple[Origin, ...] = ("general", "type", "profile")
_DEFAULT_COLOR = "green-2"
_CHANGED_COLOR = "blue-2"
_OPTION_LABEL_CLASSES = "w-40 shrink-0 text-xs text-grey-7"
_NEW_LINE = "\n"
_NEW_LINE_ESCAPE = "\\n"


def _escape(value: str) -> str:
    return value.replace(_NEW_LINE, _NEW_LINE_ESCAPE)


def _unescape(value: str) -> str:
    return value.replace(_NEW_LINE_ESCAPE, _NEW_LINE)


@dataclass
class _EntryWidgets:
    entry: QuirkEntry
    switch: ui.switch | None
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
        on = widgets.switch.value if widgets.switch is not None else default.on
        return QuirkChoice(on=on, values=values)

    def current_choices(self) -> QuirkChoices:
        return {widgets.entry.key: self._choice(widgets) for widgets in self.entries}

    def _refresh_colors(self, widgets: _EntryWidgets) -> None:
        choice = self._choice(widgets)
        for name, widget in widgets.inputs.items():
            changed = choice.values[name] != widgets.entry.default.values[name]
            color = _CHANGED_COLOR if changed else _DEFAULT_COLOR
            widget.props(f"bg-color={color}")

    def set_on(self, key: str, on: bool) -> None:
        widgets = self._widgets_for(key)
        assert widgets.switch is not None
        widgets.switch.value = on

    def set_option(self, key: str, name: str, value: str) -> None:
        self._widgets_for(key).inputs[name].value = value

    def _widgets_for(self, key: str) -> _EntryWidgets:
        return next(w for w in self.entries if w.entry.key == key)

    def _render_option(
        self, widgets: _EntryWidgets, option: QuirkOption, value: str
    ) -> None:
        widget: ui.select | ui.input | ui.number
        with ui.row().classes("w-full no-wrap items-center gap-1"):
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
            widget.classes("text-xs w-48")
            widget.on_value_change(lambda _e: self._refresh_colors(widgets))
        widgets.inputs[option.name] = widget

    def _render_entry(self, entry: QuirkEntry, choice: QuirkChoice) -> None:
        with ui.column().classes("gap-1 w-full"):
            with ui.row().classes("items-center no-wrap gap-2"):
                switch = None
                if entry.kind == "toggleable":
                    switch = ui.switch(value=choice.on).props("dense")
                    if self.readonly:
                        switch.props("disable")
                ui.label(entry.title).classes("text-sm")
                ui.badge(_KIND_LABELS[entry.kind], color="grey-6").props("outline")
            explanation = entry.explanation
            if entry.used_by:
                explanation += f" Used by: {', '.join(entry.used_by)}."
            ui.label(explanation).classes("text-xs text-grey-7")
            widgets = _EntryWidgets(entry=entry, switch=switch)
            for option in entry.options:
                self._render_option(widgets, option, choice.values[option.name])
            for detail in entry.details:
                ui.label(detail).classes("text-xs text-grey-7")
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
    origin_labels: dict[Origin, str] = {
        "general": "General",
        "type": type_label,
        "profile": "Profiles",
    }
    blocks = [
        (origin, [e for e in entries if e.origin == origin]) for origin in _ORIGIN_ORDER
    ]
    container.clear()
    with container, ui.column().classes("gap-3 w-full max-w-2xl"):
        for i, (origin, block) in enumerate(b for b in blocks if b[1]):
            if i:
                ui.separator()
            ui.label(origin_labels[origin]).classes("text-base font-bold")
            for entry in sorted(block, key=lambda e: _KIND_ORDER.index(e.kind)):
                choice = (chosen or {}).get(entry.key, entry.default)
                screen._render_entry(entry, choice)
    return screen
