from pathlib import Path

from nicegui import ui

from app.db.queries import list_activity_log, list_source_files
from app.db.session import get_engine, session_scope
from app.gui.action_panel import render_right_panel
from app.gui.import_flow import import_file, render_import_view
from app.gui.layout import shell
from app.gui.library_nav import LeftPanelNav, render_left_panel
from app.parsers.mapping import FieldMapping

_engine = get_engine()


@ui.page("/")
def home() -> None:
    panes = shell()
    nav: LeftPanelNav | None = None

    def clear_nav_selection() -> None:
        if nav is not None:
            nav.clear_selection()

    actions = render_right_panel(
        panes.right, panes.middle, on_settings=clear_nav_selection
    )

    def refresh_log() -> None:
        with session_scope(_engine) as session:
            actions.show_log(list_activity_log(session))

    def refresh(select_key: str | None = None) -> None:
        nonlocal nav
        with session_scope(_engine) as session:
            source_files = list_source_files(session)
            nav = render_left_panel(
                panes.left, panes.middle, source_files, on_import=start_import
            )
            if select_key is not None:
                nav.select(select_key)
        refresh_log()

    def on_confirmed(
        path: Path, file_type: str, mapping: FieldMapping, source: str
    ) -> None:
        with session_scope(_engine) as session:
            source_file = import_file(session, path, file_type, mapping, source)
            session.flush()
            key = f"source_file:{source_file.id}"
        refresh(select_key=key)

    def start_import() -> None:
        render_import_view(panes.middle, on_import=on_confirmed)

    refresh()
