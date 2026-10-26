from pathlib import Path

from nicegui import ui

from app.db.models import SourceFile
from app.db.queries import (
    count_records,
    count_records_for_file,
    count_records_per_file,
    count_records_per_source,
    count_records_per_year,
    list_activity_log,
    list_records,
    list_source_files,
)
from app.db.session import get_engine, session_scope
from app.db.store import remove_source_file
from app.gui.action_panel import render_right_panel
from app.gui.activity_log import clear_activity_log, log_removal
from app.gui.import_flow import import_file, render_import_view
from app.gui.layout import shell
from app.gui.library_nav import LeftPanelNav, render_left_panel
from app.gui.library_overview import (
    load_sections,
    render_library_overview,
    render_overview_settings,
    reset_sections,
    save_sections,
)
from app.gui.record_table import (
    RecordSelection,
    load_columns,
    render_record_table,
    render_table_settings,
    reset_columns,
    save_columns,
)
from app.gui.source_file_view import render_source_file_view
from app.parsers.mapping import FieldMapping

_engine = get_engine()


@ui.page("/")
def home() -> None:
    panes = shell()
    nav: LeftPanelNav | None = None
    selection = RecordSelection()

    def clear_nav_selection() -> None:
        if nav is not None:
            nav.clear_selection()

    def clear_log() -> None:
        with session_scope(_engine) as session:
            clear_activity_log(session)
        refresh_log()

    actions = render_right_panel(
        panes.right,
        panes.middle,
        on_settings=clear_nav_selection,
        on_clear_log=clear_log,
    )

    def refresh_log() -> None:
        with session_scope(_engine) as session:
            actions.show_log(list_activity_log(session))

    def show_overview() -> None:
        with session_scope(_engine) as session:
            render_library_overview(
                panes.middle,
                count_records(session),
                count_records_per_source(session),
                count_records_per_file(session),
                count_records_per_year(session),
                load_sections(session),
            )

    def save_overview_sections(sections: list[str]) -> None:
        with session_scope(_engine) as session:
            save_sections(session, sections)

    def restore_overview_sections() -> None:
        with session_scope(_engine) as session:
            reset_sections(session)
        show_overview_settings()

    def show_overview_settings() -> None:
        with session_scope(_engine) as session:
            sections = load_sections(session)
        render_overview_settings(
            panes.middle,
            sections,
            on_change=save_overview_sections,
            on_restore=restore_overview_sections,
            on_back=show_overview,
        )

    def show_table() -> None:
        with session_scope(_engine) as session:
            render_record_table(
                panes.middle, list_records(session), load_columns(session), selection
            )

    def save_table_columns(columns: list[str]) -> None:
        with session_scope(_engine) as session:
            save_columns(session, columns)

    def restore_table_columns() -> None:
        with session_scope(_engine) as session:
            reset_columns(session)
        show_table_settings()

    def show_table_settings() -> None:
        with session_scope(_engine) as session:
            columns = load_columns(session)
        render_table_settings(
            panes.middle,
            columns,
            on_change=save_table_columns,
            on_restore=restore_table_columns,
            on_back=show_table,
        )

    def show_source_file(source_file_id: int) -> None:
        with session_scope(_engine) as session:
            source_file = session.get_one(SourceFile, source_file_id)
            render_source_file_view(
                panes.middle,
                source_file,
                count_records_for_file(session, source_file_id),
                on_remove=lambda: remove_file(source_file_id),
            )

    def remove_file(source_file_id: int) -> None:
        with session_scope(_engine) as session:
            source_file = session.get_one(SourceFile, source_file_id)
            filename = source_file.filename
            removed = remove_source_file(session, source_file)
            log_removal(session, filename, removed)
        refresh()

    def refresh(select_key: str = "library:overview") -> None:
        nonlocal nav
        with session_scope(_engine) as session:
            nav = render_left_panel(
                panes.left,
                panes.middle,
                list_source_files(session),
                on_import=start_import,
                on_overview=show_overview,
                on_overview_settings=show_overview_settings,
                on_table=show_table,
                on_table_settings=show_table_settings,
                on_source_file=show_source_file,
            )
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
