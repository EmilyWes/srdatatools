import asyncio
from collections.abc import Callable
from typing import TypeVar

from nicegui import ui

T = TypeVar("T")

_DIALOG_DELAY = 0.3


async def run_busy(message: str, work: Callable[[], T]) -> T:
    task = asyncio.create_task(asyncio.to_thread(work))
    done, _ = await asyncio.wait({task}, timeout=_DIALOG_DELAY)
    if done:
        return task.result()
    # Under the page layout: a dialog nested in a closed dialog (e.g. a confirm
    # dialog that triggered this) would never render.
    with ui.context.client.layout:
        with ui.dialog().props("persistent") as dialog, ui.card():
            with ui.row().classes("items-center gap-4 no-wrap"):
                ui.spinner(size="lg")
                ui.label(message)
    dialog.open()
    try:
        return await task
    finally:
        dialog.delete()
