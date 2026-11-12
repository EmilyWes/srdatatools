from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from nicegui import ui
from nicegui.element import Element

from app.db.models import ActivityLog
from app.gui.format import format_count
from app.gui.theme import UU_GREEN, UU_ORANGE

_ACTIONS = {
    "Deduplicate": "join_full",
    "Enrich": "auto_awesome",
    "Snowball": "hub",
    "Export": "download",
}
_STATUS_CLASSES = {"ok": "log-ok", "warning": "log-warning"}
_LOG_CSS = (
    ".log-ok, .log-warning"
    " { border-left: 3px solid; padding-left: 8px; overflow-wrap: anywhere; }"
    f" .log-ok {{ border-color: {UU_GREEN}; }}"
    f" .log-warning {{ border-color: {UU_ORANGE}; }}"
)


@dataclass
class ActionPanel:
    right: Element
    log: ui.column

    def show_log(self, entries: Sequence[ActivityLog]) -> None:
        self.log.clear()
        with self.log:
            for entry in entries:
                ui.label(f"{entry.timestamp:%Y-%m-%d %H:%M}:\n{entry.message}").classes(
                    f"whitespace-pre-line {_STATUS_CLASSES[entry.status]}"
                )
        # Deferred: a once-timer waits for the browser connection before running.
        with self.right:
            ui.timer(0, self._scroll_log_to_bottom, once=True)

    def _scroll_log_to_bottom(self) -> None:
        ui.run_javascript(
            "requestAnimationFrame(() => {"
            f" const t = getHtmlElement({self.log.id});"
            " t.scrollTop = t.scrollHeight; })"
        )


def render_right_panel(
    right: Element,
    middle: Element,
    on_settings: Callable[[], Any] | None = None,
    on_clear_log: Callable[[], Any] | None = None,
    count_library: Callable[[], tuple[int, int]] | None = None,
    on_delete_library: Callable[[], Awaitable[None] | None] | None = None,
    on_export: Callable[[], Awaitable[None] | None] | None = None,
) -> ActionPanel:
    def show_settings(action: str) -> None:
        if on_settings is not None:
            on_settings()
        middle.clear()
        with middle:
            with ui.column().classes("p-6 gap-1 w-full"):
                ui.label(f"{action} settings").classes("text-2xl")
                ui.label("Not available yet.").classes(
                    "text-sm text-on-surface-variant"
                )

    def open_delete_dialog() -> None:
        source_files, records = (0, 0) if count_library is None else count_library()
        delete_message.text = (
            f"Delete all {format_count(records)} records and "
            f"{format_count(source_files)} source files from the library? "
            "This cannot be undone."
        )
        delete_dialog.open()

    def delete() -> Awaitable[None] | None:
        delete_dialog.close()
        return None if on_delete_library is None else on_delete_library()

    ui.add_css(_LOG_CSS)
    right.clear()
    with right:
        with ui.column().classes("w-full gap-2 px-3 pt-5 pb-4"):
            for action, icon in _ACTIONS.items():
                exports = action == "Export"
                with ui.row().classes("w-full items-center gap-1 no-wrap"):
                    button = (
                        ui.button(
                            action,
                            icon=icon,
                            color=None,
                            on_click=on_export if exports else None,
                        )
                        .classes("tonal nav-item flex-grow")
                        .props("no-caps align=left")
                    )
                    gear = ui.button(
                        icon="settings",
                        color=None,
                        on_click=lambda action=action: show_settings(action),
                    ).props("flat dense round size=sm")
                    gear.classes("text-on-surface-variant")
                    if exports:
                        # Export's view holds its options; the hidden gear keeps
                        # the button lined up with the others.
                        gear.classes("invisible")
                    else:
                        button.disable()
                        button.tooltip("Not implemented yet")
        # The log takes the height left over, so Delete library stays in view.
        with ui.column().classes("w-full px-3 gap-1 flex-grow min-h-0 no-wrap"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("Activity log").classes("label-medium px-1")
                ui.button("Clear log", color=None, on_click=on_clear_log).props(
                    "flat dense no-caps size=sm"
                ).classes("text-on-surface-variant px-2")
            log = ui.column().classes(
                "w-full flex-grow min-h-0 gap-3 p-3 text-xs no-wrap overflow-auto"
                " bg-white rounded-xl border outline-variant"
            )
        with ui.row().classes("w-full px-3 pt-3 pb-5"):
            ui.button(
                "Delete library",
                icon="delete_forever",
                color="negative",
                on_click=open_delete_dialog,
            ).classes("w-full").props("outline no-caps")
        with ui.dialog() as delete_dialog, ui.card():
            delete_message = ui.label()
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", color=None, on_click=delete_dialog.close).props(
                    "flat no-caps"
                )
                ui.button("Delete", color="negative", on_click=delete).props(
                    "unelevated no-caps"
                )

    return ActionPanel(right=right, log=log)
