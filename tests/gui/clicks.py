import asyncio

import pytest
from nicegui import background_tasks, core
from nicegui.element import Element


def click_and_wait(button: Element, monkeypatch: pytest.MonkeyPatch) -> None:
    click_listener = next(iter(button._event_listeners.values()))
    assert click_listener.handler is not None

    async def click() -> None:
        monkeypatch.setattr(core, "loop", asyncio.get_running_loop())
        before = set(background_tasks.running_tasks)
        click_listener.handler(None)  # type: ignore[misc]
        await asyncio.gather(*(set(background_tasks.running_tasks) - before))

    asyncio.run(click())
