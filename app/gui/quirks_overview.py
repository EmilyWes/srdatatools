from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, TypeVar

from nicegui import ui
from nicegui.element import Element

from app.parsers.mapping import FieldMapping
from app.parsers.profiles.overview import (
    ParsingChoices,
    QuirkBox,
    QuirkItem,
    QuirkList,
)

_CHANGED_BG_COLOR = "blue-2"
_CHANGED_CHECKBOX_COLOR = "blue"
# Dense boxes no taller than a line of text-sm (20px).
FIELD_CSS = """
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
# Controls line up within a box, after its longest label.
_GRID_STYLE = "grid-template-columns: max-content auto"
_GRID_CLASSES = "grid items-center gap-x-3 gap-y-1"
_CHECKBOX_SIZE = "32px"
_FIELD_CLASSES = "quirk-field text-xs"
_FIELD_WIDTH = "w-[5.5rem]"
_WIDE_FIELD_WIDTH = "w-[7rem]"
_TOOLTIP_CLASSES = "max-w-sm text-xs"
_NOTE_CLASSES = "col-span-2 text-xs text-grey-6"
_BOXES_CLASS = "quirk-boxes"
_BOX_CLASSES = "quirk-box w-fit border outline-variant rounded-xl px-3 pb-2"
# CSS can't give wrapping boxes the width of the widest one, so a script does:
# again whenever rows change, and when the hidden Parsing view is shown (hidden
# boxes measure 0). Run, not added to the head: a script added late never runs.
_EQUAL_WIDTH_JS = """
(() => {
  if (window.quirkBoxesWatched) return;
  window.quirkBoxesWatched = true;
  const equalize = (row) => {
    const boxes = [...row.querySelectorAll(":scope > .quirk-box")];
    boxes.forEach((box) => (box.style.width = ""));
    const width = Math.max(...boxes.map((box) => box.offsetWidth));
    if (width > 0) boxes.forEach((box) => (box.style.width = `${width}px`));
  };
  const watched = new WeakSet();
  const resize = new ResizeObserver((entries) =>
    entries.forEach((entry) => equalize(entry.target))
  );
  const scan = () =>
    document.querySelectorAll(".quirk-boxes").forEach((row) => {
      if (!watched.has(row)) {
        watched.add(row);
        resize.observe(row);
      }
      equalize(row);
    });
  new MutationObserver(scan).observe(document.body, {
    childList: true,
    subtree: true,
  });
  scan();
})();
"""
_TITLE_CLASSES = "mx-auto px-1 text-sm font-bold"

Widget = ui.checkbox | ui.input | ui.number | ui.select
_W = TypeVar("_W", bound=Widget)


def _shared_keys(mapping: FieldMapping) -> list[str]:
    """Keys whose target is also the target of another mapped key."""
    counts = Counter(row.target for row in mapping.rows.values())
    return [key for key, row in mapping.rows.items() if counts[row.target] > 1]


def render_box_frame(title: str) -> Element:
    """A titled box whose grid lines up each label with its control."""
    with ui.element("fieldset").classes(_BOX_CLASSES):
        with ui.element("legend").classes(_TITLE_CLASSES):
            ui.label(title)
        return ui.element("div").classes(_GRID_CLASSES).style(_GRID_STYLE)


@dataclass
class QuirksScreen:
    readonly: bool
    defaults: ParsingChoices
    current_mapping: Callable[[], FieldMapping] | None = None
    widgets: dict[str, Widget] = field(default_factory=dict)
    empty_values: list[str] = field(default_factory=list)
    use_first: list[str] = field(default_factory=list)
    empty_rows: list[ui.input] = field(default_factory=list)
    order_rows: list[ui.select] = field(default_factory=list)
    lists: dict[str, Element] = field(default_factory=dict)
    parts: dict[str, tuple[QuirkItem, ...]] = field(default_factory=dict)

    def _value(self, key: str) -> Any:
        widget = self.widgets[key]
        if isinstance(widget, ui.number):
            return int(widget.value) if widget.value else getattr(self.defaults, key)
        return widget.value

    def current_choices(self) -> ParsingChoices:
        values = {key: self._value(key) for key in self.widgets}
        lists = {
            "empty_values": [v for v in self.empty_values if v.strip()],
            "use_first": list(self.use_first),
        }
        return self.defaults.model_copy(
            update={**values, **{key: lists[key] for key in self.lists}}
        )

    def set_value(self, key: str, value: Any) -> None:
        self.widgets[key].value = value

    def _refresh_color(self, key: str) -> None:
        widget = self.widgets[key]
        changed = self._value(key) != getattr(self.defaults, key)
        if isinstance(widget, ui.checkbox):
            if changed:
                widget.props(f"color={_CHANGED_CHECKBOX_COLOR}")
            else:
                widget.props(remove="color")
        elif changed:
            widget.props(f"bg-color={_CHANGED_BG_COLOR}")
        else:
            widget.props(remove="bg-color")

    def restore_defaults(self) -> None:
        for key, widget in self.widgets.items():
            widget.value = getattr(self.defaults, key)
        defaults = self.defaults.model_dump()
        self.empty_values = list(defaults.get("empty_values", []))
        self.use_first = list(defaults.get("use_first", []))
        if "empty_values" in self.lists:
            self._render_empty_values()
        if "use_first" in self.lists:
            self.refresh_ordering()

    def _field(self, widget: _W, wide: bool = False) -> _W:
        if isinstance(widget, ui.checkbox):
            widget.props(f"dense keep-color size={_CHECKBOX_SIZE}")
            if self.readonly:
                widget.props("disable")
        else:
            width = _WIDE_FIELD_WIDTH if wide else _FIELD_WIDTH
            widget.classes(f"{_FIELD_CLASSES} {width}")
            widget.props("dense options-dense outlined")
            if self.readonly:
                widget.props("readonly")
        return widget

    def _label(self, item: QuirkItem) -> None:
        with ui.label(item.label).classes("text-xs"):
            ui.tooltip(item.hover).classes(_TOOLTIP_CLASSES)

    def _render_item(self, item: QuirkItem, value: Any) -> None:
        if item.control == "note":
            with ui.label(item.label).classes(_NOTE_CLASSES):
                ui.tooltip(item.hover).classes(_TOOLTIP_CLASSES)
            return
        self._label(item)
        widget: Widget
        if item.control == "checkbox":
            widget = ui.checkbox(value=value)
        elif item.control == "number":
            widget = ui.number(value=value, min=1, precision=0)
        else:
            widget = ui.input(value=value)
        self.widgets[item.key] = self._field(widget, item.wide)
        widget.on_value_change(lambda _e: self._refresh_color(item.key))
        self._refresh_color(item.key)

    def _wire_enabled_by(self, item: QuirkItem) -> None:
        if item.enabled_by is None or item.key not in self.widgets:
            return
        widget, toggle = self.widgets[item.key], self.widgets[item.enabled_by]

        def sync() -> None:
            widget.set_enabled(bool(toggle.value))

        toggle.on_value_change(lambda _e: sync())
        sync()

    def _remove_button(self, on_click: Callable[[], None]) -> None:
        ui.button(icon="close", on_click=on_click).props(
            "dense flat round size=xs color=negative"
        )

    def _shown_rows(self, entries: list[Any], blank: Any) -> list[Any]:
        """An editable list ends in a blank entry; picking in it adds the next."""
        return entries if self.readonly else [*entries, blank]

    def _render_empty_values(self) -> None:
        container = self.lists["empty_values"]
        container.clear()
        self.empty_rows = []
        with container:
            for index, value in enumerate(self._shown_rows(self.empty_values, "")):
                self._add_empty_row(index, value)

    def _add_empty_row(self, index: int, value: str) -> None:
        [part] = self.parts["empty_values"]
        self._label(part)
        with ui.row().classes("no-wrap items-center gap-1"):
            text = self._field(ui.input(value=value), part.wide)
            if not (self.readonly or index == len(self.empty_values)):
                self._remove_button(partial(self._remove_empty, index))
        text.on_value_change(lambda e, i=index: self._type_empty(i, e.value))
        self.empty_rows.append(text)

    def _type_empty(self, index: int, value: str) -> None:
        """Typing in the blank box adds the next one without a redraw, so the
        cursor stays in the box being typed in."""
        if index < len(self.empty_values):
            self.empty_values[index] = value
            return
        if not value:
            return
        self.empty_values.append(value)
        row = self.empty_rows[index].parent_slot
        assert row is not None
        with row.parent:
            self._remove_button(partial(self._remove_empty, index))
        with self.lists["empty_values"]:
            self._add_empty_row(len(self.empty_values), "")

    def _remove_empty(self, index: int) -> None:
        del self.empty_values[index]
        self._render_empty_values()

    def refresh_ordering(self) -> None:
        """Offers the keys that share a target in the current mapping."""
        container = self.lists["use_first"]
        [part] = self.parts["use_first"]
        shared = _shared_keys(self.current_mapping()) if self.current_mapping else []
        container.clear()
        self.order_rows = []
        rows = self._shown_rows(self.use_first, "")
        with container:
            for index, chosen in enumerate(rows):
                taken = {key for i, key in enumerate(rows) if i != index}
                keys = [k for k in shared if k not in taken]
                if chosen and chosen not in keys:
                    keys.append(chosen)
                self._label(part)
                with ui.row().classes("no-wrap items-center gap-1"):
                    select = self._field(ui.select(keys, value=chosen or None))
                    if not (self.readonly or index == len(self.use_first)):
                        self._remove_button(partial(self._remove_order, index))
                select.on_value_change(lambda e, i=index: self._pick_order(i, e.value))
                self.order_rows.append(select)

    def _pick_order(self, index: int, value: str | None) -> None:
        if index == len(self.use_first):
            self.use_first.append(value or "")
        else:
            self.use_first[index] = value or ""
        self.use_first = [key for key in self.use_first if key]
        self.refresh_ordering()

    def _remove_order(self, index: int) -> None:
        del self.use_first[index]
        self.refresh_ordering()

    def _render_list(self, item: QuirkList) -> None:
        self.parts[item.key] = item.parts
        self.lists[item.key] = (
            ui.element("div").classes(f"{_GRID_CLASSES} col-span-2").style(_GRID_STYLE)
        )
        if item.key == "empty_values":
            self._render_empty_values()
        else:
            self.refresh_ordering()

    def render_box(self, box: QuirkBox, chosen: ParsingChoices) -> None:
        with render_box_frame(box.title):
            for item in box.items:
                if isinstance(item, QuirkList):
                    self._render_list(item)
                else:
                    self._render_item(item, getattr(chosen, item.key, None))
        for item in box.items:
            if isinstance(item, QuirkItem):
                self._wire_enabled_by(item)


VIEW_MAPPING = "mapping"
VIEW_PARSING = "parsing"
_STACKED_CLASSES = "col-start-1 row-start-1"
_HIDDEN_VIEW_CLASSES = "h-0 overflow-hidden invisible"


@dataclass
class MappingParsingViews:
    toggle: ui.toggle
    mapping: ui.column
    parsing: ui.column

    def show(self, view: str | None) -> None:
        for container, name in (
            (self.mapping, VIEW_MAPPING),
            (self.parsing, VIEW_PARSING),
        ):
            if view == name:
                container.classes(remove=_HIDDEN_VIEW_CLASSES)
            else:
                container.classes(add=_HIDDEN_VIEW_CLASSES)


def render_view_toggle(
    view: str | None = None,
    on_change: Callable[[str | None], Any] | None = None,
    parsing_label: str = "Parsing",
) -> MappingParsingViews:
    """The Mapping | Parsing toggle above two containers, at most one shown.

    Clicking the shown view's button hides it (`view` None).
    Both share one grid cell whose width only the mapping sets, so toggling
    doesn't resize the middle pane: Parsing wraps its boxes to that width, and
    the hidden view is collapsed rather than removed so its width still counts.
    """
    options = {VIEW_MAPPING: "Mapping", VIEW_PARSING: parsing_label}
    toggle = (
        ui.toggle(options, value=view, clearable=True)
        .props("dense no-caps unelevated rounded toggle-color=secondary")
        .classes("segmented")
    )
    with ui.element("div").classes("grid w-fit max-w-full"):
        mapping = ui.column().classes(_STACKED_CLASSES)
        parsing = ui.column().classes(f"{_STACKED_CLASSES} w-0 min-w-full")
    views = MappingParsingViews(toggle=toggle, mapping=mapping, parsing=parsing)

    def change(value: str | None) -> None:
        views.show(value)
        if on_change is not None:
            on_change(value)

    views.toggle.on_value_change(lambda e: change(e.value))
    views.show(view)
    return views


def render_quirks_overview(
    container: Element,
    boxes: list[QuirkBox],
    defaults: ParsingChoices,
    chosen: ParsingChoices | None = None,
    current_mapping: Callable[[], FieldMapping] | None = None,
) -> QuirksScreen:
    """`chosen` shows a stored import's choices read-only."""
    shown = chosen or defaults
    lists = shown.model_dump()
    screen = QuirksScreen(
        readonly=chosen is not None,
        defaults=defaults,
        current_mapping=current_mapping,
        empty_values=list(lists.get("empty_values", [])),
        use_first=list(lists.get("use_first", [])),
    )
    ui.add_css(FIELD_CSS)
    container.clear()
    with container, ui.column().classes("gap-1 w-full"):
        # Deferred: a once-timer waits for the browser connection before running.
        ui.timer(0, lambda: ui.run_javascript(_EQUAL_WIDTH_JS), once=True)
        with ui.row().classes(f"{_BOXES_CLASS} w-full items-start gap-3 pl-3"):
            for box in boxes:
                screen.render_box(box, shown)
        if not screen.readonly:
            with ui.row().classes("w-full justify-end"):
                ui.button("Restore defaults", on_click=screen.restore_defaults).props(
                    "dense flat no-caps"
                ).classes("text-xs")
    return screen
