import datetime
from typing import Any

import pytest
from nicegui import ui
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

import app.gui.home as home_module
import app.main
from app.db.models import ActivityLog, Base, SourceFile
from app.gui.action_panel import ActionPanel
from app.gui.home import home
from app.gui.layout import ShellPanes


@pytest.fixture(autouse=True)
def engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(home_module, "_engine", engine)
    return engine


def test_home__builds_without_raising() -> None:
    home()


def test_main__importable_without_launching_ui_run() -> None:
    assert callable(app.main.main)


def test_home__shows_activity_log_entries_in_right_panel(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(engine) as session:
        session.add(
            ActivityLog(
                timestamp=datetime.datetime(2026, 1, 1, 9, 5),
                action_type="import",
                message="Imported 5 records",
            )
        )
        session.commit()
    panels: list[ActionPanel] = []
    render_right_panel = home_module.render_right_panel

    def capture(*args: Any, **kwargs: Any) -> ActionPanel:
        panel = render_right_panel(*args, **kwargs)
        panels.append(panel)
        return panel

    monkeypatch.setattr(home_module, "render_right_panel", capture)

    home()

    assert panels[0].log.value == "2026-01-01 09:05  Imported 5 records"


def test_home__shows_library_overview_on_start(monkeypatch: pytest.MonkeyPatch) -> None:
    shells: list[ShellPanes] = []
    shell = home_module.shell

    def capture() -> ShellPanes:
        panes = shell()
        shells.append(panes)
        return panes

    monkeypatch.setattr(home_module, "shell", capture)

    home()

    labels = [
        element.text
        for element in shells[0].middle.descendants()
        if isinstance(element, ui.label)
    ]
    assert "Total records" in labels


def test_home__builds_with_imported_source_file(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(
            SourceFile(
                filename="scopus.ris",
                path=None,
                format="ris",
                imported_at=datetime.datetime(2026, 1, 1),
                row_count=1,
            )
        )
        session.commit()

    home()
