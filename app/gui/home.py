import logging
from pathlib import Path
from typing import Any

from nicegui import ui

from app.cleaning.options import CleaningOptions
from app.cleaning.options import load_options as load_cleaning_options
from app.cleaning.options import save_options as save_cleaning_options
from app.db.activity_log import (
    clear_activity_log,
    log_cleaning,
    log_export,
    log_export_failed,
    log_import_failed,
    log_library_deleted,
    log_records_deleted,
    log_removal,
)
from app.db.models import SourceFile
from app.db.queries import (
    count_data_quality,
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
    load_export_records,
)
from app.db.session import get_engine, session_scope
from app.db.store import (
    clean_records,
    delete_library,
    delete_records,
    remove_source_file,
)
from app.export.columns import ExportColumn, ExportRecord
from app.export.csv_ import write_csv
from app.export.options import (
    ExportOptions,
    load_options,
    reset_options,
    save_options,
)
from app.gui.about import render_about_view, render_help_view
from app.gui.action_panel import render_right_panel
from app.gui.busy import run_busy
from app.gui.cleaning_flow import render_cleaning_view
from app.gui.export_flow import render_export_view
from app.gui.format import format_count
from app.gui.import_flow import import_file, render_import_view
from app.gui.layout import shell
from app.gui.library_dashboard import (
    COMPLETENESS_FIELDS,
    dashboard_items,
    load_hidden,
    render_dashboard_settings,
    render_library_dashboard,
    reset_hidden,
    save_hidden,
)
from app.gui.library_nav import LeftPanelNav, render_left_panel
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
from app.parsers.common import FileSummary, FileType
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
        on_export=lambda: start_export(),
        on_cleaning=lambda: start_cleaning(),
    )

    def refresh_log() -> None:
        with session_scope(_engine) as session:
            actions.show_log(list_activity_log(session))

    def show_dashboard() -> None:
        with session_scope(_engine) as session:
            filled = count_filled_fields(session, COMPLETENESS_FIELDS)
            render_library_dashboard(
                panes.middle,
                count_records(session),
                [(COLUMNS[key], count) for key, count in filled],
                count_data_quality(session),
                count_records_per_year(session),
                count_publication_types(session),
                count_records_per_source_file(session),
                count_label_values(session),
                count_keywords(session),
                load_hidden(session),
            )

    def save_dashboard_hidden(hidden: set[str]) -> None:
        with session_scope(_engine) as session:
            save_hidden(session, hidden)

    def restore_dashboard_hidden() -> None:
        with session_scope(_engine) as session:
            reset_hidden(session)
        show_dashboard_settings()

    def show_dashboard_settings() -> None:
        with session_scope(_engine) as session:
            items = dashboard_items(
                list_label_columns(session), list(count_keywords(session))
            )
            hidden = load_hidden(session)
        render_dashboard_settings(
            panes.middle,
            items,
            hidden,
            on_change=save_dashboard_hidden,
            on_restore=restore_dashboard_hidden,
            on_back=show_dashboard,
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

    def refresh(select_key: str = "library:dashboard") -> None:
        nonlocal nav
        with session_scope(_engine) as session:
            nav = render_left_panel(
                panes.left,
                list_source_files(session),
                on_import=start_import,
                on_dashboard=show_dashboard,
                on_dashboard_settings=show_dashboard_settings,
                on_table=show_table,
                on_table_settings=show_table_settings,
                on_source_file=show_source_file,
                on_about=lambda: render_about_view(panes.middle),
                on_help=lambda: render_help_view(panes.middle),
            )
        nav.select(select_key)
        refresh_log()

    async def on_confirmed(
        files: list[tuple[Path, FileSummary]],
        file_type: FileType,
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

    async def export(
        path: Path,
        columns: list[ExportColumn],
        records: list[ExportRecord],
        options: ExportOptions,
    ) -> None:
        def write() -> tuple[int, str | None]:
            try:
                cut = write_csv(path, columns, records, options)
            except OSError as exc:
                logger.warning("Could not export to %s", path, exc_info=True)
                with session_scope(_engine) as session:
                    log_export_failed(session, path.name, str(exc))
                return 0, str(exc)
            with session_scope(_engine) as session:
                log_export(session, path.name, len(records), cut)
            return cut, None

        cut, error = await run_busy(f"Exporting to {path.name}…", write)
        if error is not None:
            with panes.middle:
                ui.notify(f"Could not export to {path.name}: {error}", type="negative")
            refresh_log()
            return
        noun = "record" if len(records) == 1 else "records"
        message = f"Exported {format_count(len(records))} {noun} to {path.name}"
        if cut:
            message += (
                f"; {format_count(cut)} values cut to"
                f" {format_count(options.max_length)} characters"
            )
        with panes.middle:
            ui.notify(message, type="warning" if cut else "positive")
        refresh()

    def save_export_options(options: ExportOptions) -> None:
        with session_scope(_engine) as session:
            save_options(session, options)

    def restore_export_options() -> None:
        with session_scope(_engine) as session:
            reset_options(session)

    async def start_export() -> None:
        clear_nav_selection()
        ids = set(selection.ids) or None

        def load() -> tuple[list[ExportRecord], ExportOptions]:
            with session_scope(_engine) as session:
                return load_export_records(session, ids), load_options(session)

        records, options = await run_busy("Loading records…", load)
        render_export_view(
            panes.middle,
            records,
            options,
            selected=ids is not None,
            on_export=export,
            on_options_change=save_export_options,
            on_restore_options=restore_export_options,
        )

    async def start_cleaning() -> None:
        clear_nav_selection()
        ids = set(selection.ids) or None

        def load() -> tuple[int, CleaningOptions]:
            with session_scope(_engine) as session:
                count = count_records(session) if ids is None else len(ids)
                return count, load_cleaning_options(session)

        async def clean(options: CleaningOptions) -> None:
            def run() -> tuple[int, int]:
                with session_scope(_engine) as session:
                    save_cleaning_options(session, options)
                    total, changed, per_step = clean_records(session, options, ids)
                    log_cleaning(session, total, changed, per_step)
                return total, changed

            total, changed = await run_busy("Cleaning records…", run)
            noun = "record" if total == 1 else "records"
            with panes.middle:
                ui.notify(
                    f"Cleaned {format_count(total)} {noun}:"
                    f" {format_count(changed)} changed",
                    type="positive",
                )
            if nav is not None:
                nav.select("library:dashboard")
            refresh_log()

        count, options = await run_busy("Loading cleaning options…", load)
        render_cleaning_view(
            panes.middle, count, options, selected=ids is not None, on_clean=clean
        )

    def start_import() -> None:
        render_import_view(panes.middle, on_import=on_confirmed)

    refresh()
