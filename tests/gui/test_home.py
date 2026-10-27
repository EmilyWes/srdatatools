import asyncio
import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from nicegui import ui
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

import app.gui.home as home_module
import app.main
from app.db.models import ActivityLog, Base, Record, RecordSource, SourceFile
from app.gui.action_panel import ActionPanel
from app.gui.home import home
from app.gui.layout import ShellPanes
from app.gui.library_nav import LeftPanelNav
from app.gui.library_overview import save_sections
from app.parsers.common import FileSummary
from app.parsers.mapping import FieldMapping
from tests.gui.clicks import click_and_wait


@pytest.fixture(autouse=True)
def engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Engine:
    # File-based: slow actions run in a worker thread, which can't see :memory:.
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
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

    labels = panels[0].log.default_slot.children
    assert [label.text for label in labels] == [  # type: ignore[attr-defined]
        "2026-01-01 09:05:\nImported 5 records"
    ]


def test_home__clear_log_empties_db_and_right_panel(
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
    clear_button = next(
        element
        for element in panels[0].right.descendants()
        if isinstance(element, ui.button) and element.text == "Clear log"
    )
    click_listener = next(iter(clear_button._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)

    with Session(engine) as session:
        assert session.query(ActivityLog).count() == 0
    assert panels[0].log.default_slot.children == []


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


def test_home__overview_shows_only_stored_sections(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(engine) as session:
        save_sections(session, ["per_year"])
        session.commit()
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
    assert "Records per year" in labels
    assert "Total records" not in labels


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


def _add_source_file_with_record(engine: Engine) -> int:
    with Session(engine) as session:
        source_file = SourceFile(
            filename="scopus.ris",
            path=None,
            format="ris",
            imported_at=datetime.datetime(2026, 1, 1),
            row_count=1,
            field_mapping=asdict(FieldMapping(targets={"TI": "title"})),
            suggested_mapping=asdict(FieldMapping(targets={"TI": "title"})),
            file_summary=asdict(FileSummary({"TI": "A title"}, {"TI": 1}, 1)),
        )
        session.add(
            Record(title="A title", sources=[RecordSource(source_file=source_file)])
        )
        session.commit()
        return source_file.id


def _capture_navs(monkeypatch: pytest.MonkeyPatch) -> list[LeftPanelNav]:
    navs: list[LeftPanelNav] = []
    render_left_panel = home_module.render_left_panel

    def capture(*args: Any, **kwargs: Any) -> LeftPanelNav:
        nav = render_left_panel(*args, **kwargs)
        navs.append(nav)
        return nav

    monkeypatch.setattr(home_module, "render_left_panel", capture)
    return navs


def _capture_removes(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    on_removes: list[Any] = []
    render_source_file_view = home_module.render_source_file_view

    def capture(*args: Any, **kwargs: Any) -> None:
        on_removes.append(kwargs["on_remove"])
        render_source_file_view(*args, **kwargs)

    monkeypatch.setattr(home_module, "render_source_file_view", capture)
    return on_removes


def test_home__import_stores_given_summary_and_selects_new_file(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nA title\n")
    summary = FileSummary({"Title": "From the mapping screen"}, {"Title": 1}, 1)
    navs = _capture_navs(monkeypatch)
    on_imports: list[Any] = []
    monkeypatch.setattr(
        home_module,
        "render_import_view",
        lambda middle, on_import: on_imports.append(on_import),
    )

    home()
    click_and_wait(navs[-1].buttons["import"], monkeypatch)
    middle = navs[-1].middle

    async def confirm() -> None:
        with middle:
            await on_imports[-1](
                csv_path,
                "csv",
                FieldMapping(targets={"Title": "title"}),
                "unknown",
                summary,
            )

    asyncio.run(confirm())

    with Session(engine) as session:
        source_file = session.query(SourceFile).one()
        assert source_file.file_summary == asdict(summary)
        assert session.query(Record).one().title == "A title"
    assert navs[-1].selected_key == f"source_file:{source_file.id}"


def test_home__clicking_table_shows_records_in_grid(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_source_file_with_record(engine)
    navs = _capture_navs(monkeypatch)

    home()
    click_and_wait(navs[-1].buttons["library:table"], monkeypatch)

    grid = next(
        element
        for element in navs[-1].middle.descendants()
        if isinstance(element, ui.aggrid)
    )
    assert [row["title"] for row in grid.options["rowData"]] == ["A title"]


def test_home__selecting_source_file_shows_detail_view(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file_id = _add_source_file_with_record(engine)
    navs = _capture_navs(monkeypatch)

    home()
    navs[-1].select(f"source_file:{source_file_id}")

    labels = [
        element.text
        for element in navs[-1].middle.descendants()
        if isinstance(element, ui.label)
    ]
    assert "Records in library" in labels


def test_home__removing_source_file_deletes_logs_and_shows_overview(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file_id = _add_source_file_with_record(engine)
    navs = _capture_navs(monkeypatch)
    on_removes = _capture_removes(monkeypatch)

    home()
    navs[-1].select(f"source_file:{source_file_id}")
    middle = navs[-1].middle

    async def remove() -> None:
        with middle:
            await on_removes[-1]()

    asyncio.run(remove())

    with Session(engine) as session:
        assert session.query(SourceFile).count() == 0
        assert session.query(Record).count() == 0
        assert session.query(ActivityLog).one().action_type == "remove"
    assert navs[-1].selected_key == "library:overview"
    assert f"source_file:{source_file_id}" not in navs[-1].buttons
