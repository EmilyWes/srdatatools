from nicegui import ui

from app.db.queries import list_source_files
from app.db.session import get_engine, session_scope
from app.gui.layout import shell
from app.gui.library_nav import render_left_panel

_engine = get_engine()


@ui.page("/")
def home() -> None:
    panes = shell()
    with session_scope(_engine) as session:
        source_files = list_source_files(session)
        render_left_panel(panes.left, panes.middle, source_files)
