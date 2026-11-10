import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest
from nicegui import background_tasks, core
from nicegui.element import Element
from nicegui.events import ClickEventArguments

T = TypeVar("T")


def click_and_wait(button: Element, monkeypatch: pytest.MonkeyPatch) -> None:
    click_listener = next(iter(button._event_listeners.values()))
    assert click_listener.handler is not None

    async def click() -> None:
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        before = set(background_tasks.running_tasks)
        click_listener.handler(  # type: ignore[misc]
            ClickEventArguments(sender=button, client=button.client)
        )
        await asyncio.gather(*(set(background_tasks.running_tasks) - before))

    asyncio.run(click())


def run_in(element: Element, handler: Coroutine[Any, Any, T]) -> T:
    """Awaits a handler inside element's slot, as NiceGUI does for event handlers."""

    async def run() -> T:
        with element:
            return await handler

    return asyncio.run(run())
