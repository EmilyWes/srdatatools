from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from nicegui import ui
from nicegui.element import Element

from app.db.models import ActivityLog

_ACTIONS = ["Dedup", "Enrich", "Snowball", "Export"]


@dataclass
class ActionPanel:
    right: Element
    log: ui.textarea

    def show_log(self, entries: Sequence[ActivityLog]) -> None:
        self.log.value = "\n".join(
            f"{entry.timestamp:%Y-%m-%d %H:%M}  {entry.message}" for entry in entries
        )
        # Deferred: a once-timer waits for the browser connection before running.
        with self.right:
            ui.timer(0, self._scroll_log_to_bottom, once=True)

    def _scroll_log_to_bottom(self) -> None:
        ui.run_javascript(
            "requestAnimationFrame(() => {"
            f" const t = getHtmlElement({self.log.id}).querySelector('textarea');"
            " t.scrollTop = t.scrollHeight; })"
        )


def render_right_panel(
    right: Element,
    middle: Element,
    on_settings: Callable[[], Any] | None = None,
) -> ActionPanel:
    def show_settings(action: str) -> None:
        if on_settings is not None:
            on_settings()
        middle.clear()
        with middle:
            with ui.column().classes("pt-4 items-center w-full"):
                ui.label(f"{action} settings").classes("text-lg")
                ui.label("Not available yet.").classes("text-sm text-grey-6")

    right.clear()
    with right:
        with ui.column().classes("w-full items-center gap-2 pt-4"):
            for action in _ACTIONS:
                with ui.row().classes("items-center gap-1 no-wrap"):
                    button = (
                        ui.button(action, color=None)
                        .classes("w-32 text-sm")
                        .props("dense")
                    )
                    button.disable()
                    button.tooltip("Not implemented yet")
                    ui.button(
                        icon="settings",
                        color=None,
                        on_click=lambda action=action: show_settings(action),
                    ).props("flat dense round size=sm")
        log = (
            ui.textarea("Activity log")
            .props("readonly outlined")
            .classes("w-full flex-grow px-2 pb-2 text-xs")
        )

    return ActionPanel(right=right, log=log)
