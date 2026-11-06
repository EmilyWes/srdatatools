import logging
from pathlib import Path
from typing import Any

from nicegui import ui

from app.db.models import SourceFile
from app.db.queries import (
    count_filled_fields,
    count_keywords,
    count_label_values,
    count_publication_types,
    count_records,
    count_records_for_file,
    count_records_per_source_file,
    count_records_per_year,
    list_activity_log,
    list_label_columns,
    list_source_files,
)
from app.db.session import get_engine, session_scope
from app.db.store import delete_library, delete_records, remove_source_file
from app.gui.action_panel import render_right_panel
from app.gui.activity_log import (
    clear_activity_log,
    log_import_failed,
    log_library_deleted,
    log_records_deleted,
    log_removal,
)
from app.gui.busy import run_busy
from app.gui.import_flow import import_file, render_import_view
from app.gui.layout import shell
from app.gui.library_nav import LeftPanelNav, render_left_panel
from app.gui.library_overview import (
    COMPLETENESS_FIELDS,
    load_hidden,
    overview_items,
    render_library_overview,
    render_overview_settings,
    reset_hidden,
    save_hidden,
)
from app.gui.record_table import (
    COLUMNS,
    LabelFormat,
    RecordSelection,
    load_columns,
    load_keyword_columns,
    load_label_columns,
    load_label_format,
    load_rows,
    render_record_table,
    render_table_settings,
    reset_columns,
    reset_label_format,
    save_columns,
    save_label_format,
)
from app.gui.source_file_view import render_source_file_view
from app.parsers.common import FileSummary
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.overview import ParsingChoices

logger = logging.getLogger(__name__)

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

    def count_library() -> tuple[int, int]:
        with session_scope(_engine) as session:
            return len(list_source_files(session)), count_records(session)

    async def delete_all() -> None:
        def delete() -> None:
            with session_scope(_engine) as session:
                source_files, records = delete_library(session)
                log_library_deleted(session, source_files, records)

        await run_busy("Deleting library…", delete)
        refresh()

    actions = render_right_panel(
        panes.right,
        panes.middle,
        on_settings=clear_nav_selection,
        on_clear_log=clear_log,
        count_library=count_library,
        on_delete_library=delete_all,
    )

    def refresh_log() -> None:
        with session_scope(_engine) as session:
            actions.show_log(list_activity_log(session))

    def show_overview() -> None:
        with session_scope(_engine) as session:
            filled = count_filled_fields(session, COMPLETENESS_FIELDS)
            render_library_overview(
                panes.middle,
                count_records(session),
                [(COLUMNS[key], count) for key, count in filled],
                count_records_per_year(session),
                count_publication_types(session),
                count_records_per_source_file(session),
                count_label_values(session),
                count_keywords(session),
                load_hidden(session),
            )

    def save_overview_hidden(hidden: set[str]) -> None:
        with session_scope(_engine) as session:
            save_hidden(session, hidden)

    def restore_overview_hidden() -> None:
        with session_scope(_engine) as session:
            reset_hidden(session)
        show_overview_settings()

    def show_overview_settings() -> None:
        with session_scope(_engine) as session:
            items = overview_items(
                list_label_columns(session), list(count_keywords(session))
            )
            hidden = load_hidden(session)
        render_overview_settings(
            panes.middle,
            items,
            hidden,
            on_change=save_overview_hidden,
            on_restore=restore_overview_hidden,
            on_back=show_overview,
        )

    async def show_table() -> None:
        def load() -> tuple[list[dict[str, Any]], list[str]]:
            with session_scope(_engine) as session:
                columns = load_columns(session)
                label_format = load_label_format(session)
                return load_rows(session, columns, label_format), columns

        rows, columns = await run_busy("Loading library table…", load)
        render_record_table(
            panes.middle, rows, columns, selection, on_delete=delete_selected
        )

    async def delete_selected(ids: set[int]) -> None:
        def delete() -> None:
            with session_scope(_engine) as session:
                log_records_deleted(session, delete_records(session, ids))

        await run_busy("Deleting records…", delete)
        selection.ids.clear()
        refresh_log()
        await show_table()

    def save_table_columns(columns: list[str]) -> None:
        with session_scope(_engine) as session:
            save_columns(session, columns)

    def save_table_label_format(label_format: LabelFormat) -> None:
        with session_scope(_engine) as session:
            save_label_format(session, label_format)

    def restore_table_columns() -> None:
        with session_scope(_engine) as session:
            reset_columns(session)
            reset_label_format(session)
        show_table_settings()

    def show_table_settings() -> None:
        with session_scope(_engine) as session:
            columns = load_columns(session)
            label_columns = load_label_columns(session)
            keyword_columns = load_keyword_columns(session)
            label_format = load_label_format(session)
        render_table_settings(
            panes.middle,
            columns,
            label_columns=label_columns,
            keyword_columns=keyword_columns,
            label_format=label_format,
            on_change=save_table_columns,
            on_label_format=save_table_label_format,
            on_restore=restore_table_columns,
            on_back=show_table,
        )

    def show_source_file(source_file_id: int) -> None:
        with session_scope(_engine) as session:
            source_file = session.get_one(SourceFile, source_file_id)
            filename = source_file.filename
            render_source_file_view(
                panes.middle,
                source_file,
                count_records_for_file(session, source_file_id),
                on_remove=lambda: remove_file(source_file_id, filename),
            )

    async def remove_file(source_file_id: int, filename: str) -> None:
        def remove() -> None:
            with session_scope(_engine) as session:
                source_file = session.get_one(SourceFile, source_file_id)
                removed = remove_source_file(session, source_file)
                log_removal(session, filename, removed)

        await run_busy(f"Removing {filename}…", remove)
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

    async def on_confirmed(
        files: list[tuple[Path, FileSummary]],
        file_type: str,
        mapping: FieldMapping,
        source: str,
        sheet: str | None,
        choices: ParsingChoices,
    ) -> None:
        def store() -> tuple[list[int], list[tuple[str, str]]]:
            """Each file is stored on its own, so one that fails doesn't undo
            the others."""
            source_file_ids: list[int] = []
            failures: list[tuple[str, str]] = []
            for path, summary in files:
                try:
                    with session_scope(_engine) as session:
                        source_file = import_file(
                            session,
                            path,
                            file_type,
                            mapping,
                            summary,
                            source,
                            sheet,
                            choices,
                        )
                        session.flush()
                        source_file_ids.append(source_file.id)
                except (ValueError, OSError) as exc:
                    logger.warning("Could not import %s", path, exc_info=True)
                    failures.append((path.name, str(exc)))
                    with session_scope(_engine) as session:
                        log_import_failed(session, path.name, str(exc))
            return source_file_ids, failures

        name = files[0][0].name if len(files) == 1 else f"{len(files)} files"
        source_file_ids, failures = await run_busy(f"Importing {name}…", store)
        with panes.middle:
            for filename, reason in failures:
                ui.notify(f"Could not import {filename}: {reason}", type="negative")
        if len(source_file_ids) == 1:
            refresh(select_key=f"source_file:{source_file_ids[0]}")
        else:
            refresh()

    def start_import() -> None:
        render_import_view(panes.middle, on_import=on_confirmed)

    refresh()
