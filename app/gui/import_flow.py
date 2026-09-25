from collections.abc import Callable
from pathlib import Path

from nicegui import app, ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.models import SourceFile
from app.db.store import store_parsed_rows
from app.gui.csv_mapping import render_csv_mapping
from app.parsers.csv_ import ColumnMapping, parse_csv_file, read_csv_headers


async def pick_file() -> Path | None:
    assert app.native.main_window is not None, "native window is not running"
    selected = await app.native.main_window.create_file_dialog(allow_multiple=False)
    return Path(selected[0]) if selected else None


def show_csv_mapping(
    middle: Element, path: Path, on_confirm: Callable[[Path, ColumnMapping], None]
) -> None:
    try:
        headers = read_csv_headers(path)
    except ValueError as exc:
        with middle:
            ui.notify(str(exc), type="negative")
        return

    if not headers:
        with middle:
            ui.notify(f"{path.name} has no columns to map", type="negative")
        return

    render_csv_mapping(middle, headers, lambda mapping: on_confirm(path, mapping))


def import_csv(session: Session, path: Path, mapping: ColumnMapping) -> SourceFile:
    result = parse_csv_file(path, mapping)
    return store_parsed_rows(
        session,
        filename=path.name,
        path=str(path),
        format="csv",
        parsed_rows=[(row.record, row.raw_fields) for row in result.rows],
    )


def import_file(session: Session, path: Path, mapping: ColumnMapping) -> SourceFile:
    """Detects type from the file extension and dispatches to the matching
    parser; only CSV is implemented so far. This is the seam later
    Source/Type-dropdown work will plug into.
    """
    if path.suffix.lower() != ".csv":
        raise ValueError(f"unsupported file type: {path.suffix!r}")
    return import_csv(session, path, mapping)
