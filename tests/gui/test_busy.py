import asyncio
import threading
from collections.abc import Callable, Iterator
from typing import TypeVar

import pytest
from nicegui import ui

from app.gui.busy import run_busy
from app.gui.layout import shell

T = TypeVar("T")


_preexisting_dialog_ids: set[int] = set()


@pytest.fixture(autouse=True)
def _ignore_preexisting_dialogs() -> Iterator[None]:
    # The client layout is shared by every test in the run, so other tests'
    # dialogs may already be there.
    _preexisting_dialog_ids.update(dialog.id for dialog in _all_dialogs())
    yield
    _preexisting_dialog_ids.clear()


def _all_dialogs() -> list[ui.dialog]:
    return [
        element
        for element in ui.context.client.layout.descendants()
        if isinstance(element, ui.dialog)
    ]


def _dialogs() -> list[ui.dialog]:
    return [
        dialog for dialog in _all_dialogs() if dialog.id not in _preexisting_dialog_ids
    ]


def _dialog_labels() -> list[str]:
    return [
        element.text
        for dialog in _dialogs()
        for element in dialog.descendants()
        if isinstance(element, ui.label)
    ]


def _run_busy_in_page(message: str, work: Callable[[], T]) -> T:
    middle = shell().middle

    async def run() -> T:
        with middle:
            return await run_busy(message, work)

    return asyncio.run(run())


def _slow(result: T) -> Callable[[], T]:
    def work() -> T:
        threading.Event().wait(0.5)
        return result

    return work


def test_run_busy__returns_result_without_dialog_when_fast() -> None:
    result = _run_busy_in_page("Working…", lambda: 42)

    assert result == 42
    assert _dialogs() == []


def test_run_busy__shows_message_dialog_when_slow() -> None:
    middle = shell().middle
    release = threading.Event()
    seen: list[list[str]] = []

    async def look_then_release() -> None:
        try:
            await asyncio.sleep(0.5)
            with middle:
                seen.append(_dialog_labels())
        finally:
            release.set()

    async def scenario() -> None:
        checker = asyncio.create_task(look_then_release())
        with middle:
            await run_busy("Importing big.ris…", release.wait)
        await checker

    asyncio.run(scenario())

    assert seen == [["Importing big.ris…"]]


def test_run_busy__removes_dialog_after_work_finishes() -> None:
    result = _run_busy_in_page("Working…", _slow("done"))

    assert result == "done"
    assert _dialogs() == []


def test_run_busy__removes_dialog_and_reraises_when_work_fails() -> None:
    def work() -> None:
        _slow(None)()
        raise ValueError("bad file")

    with pytest.raises(ValueError, match="bad file"):
        _run_busy_in_page("Working…", work)

    assert _dialogs() == []
