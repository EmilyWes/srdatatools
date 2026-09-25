import asyncio
import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.gui import import_flow
from app.gui.import_flow import (
    ImportView,
    import_csv,
    import_file,
    pick_file,
    render_import_view,
    render_mapping,
)
from app.gui.layout import shell
from app.parsers.csv_ import ColumnMapping


class _FakeWindow:
    def __init__(self, result: tuple[str, ...] | None) -> None:
        self._result = result

    async def create_file_dialog(self, **kwargs: Any) -> tuple[str, ...] | None:
        return self._result


@pytest.fixture
def engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine: Engine) -> Session:
    return sessionmaker(bind=engine)()


def test_pick_file__returns_path_when_file_selected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    picked = tmp_path / "export.csv"
    monkeypatch.setattr(
        import_flow.app.native, "main_window", _FakeWindow((str(picked),))
    )

    result = asyncio.run(pick_file())

    assert result == picked


def test_pick_file__returns_none_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_flow.app.native, "main_window", _FakeWindow(None))

    result = asyncio.run(pick_file())

    assert result is None


def test_render_mapping__renders_mapping_screen_with_file_headers(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path)

    assert screen is not None
    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input, no button
    header_rows = middle_children[0].default_slot.children
    assert len(header_rows) == 3  # column header labels row + one row per CSV column


def test_render_mapping__notifies_and_returns_none_when_file_cannot_be_decoded(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(b"\x81")  # undefined in both utf-8-sig and cp1252
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path)  # must not raise

    assert screen is None


def test_render_mapping__returns_none_for_non_csv_type(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    panes = shell()

    screen = render_mapping(panes.middle, "unknown", csv_path)

    assert screen is None


def test_import_csv__stores_records_and_returns_source_file_with_row_count(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\nOther Paper,10.1/abc\n")
    mapping = ColumnMapping(fields={"Title": "title", "DOI": "doi"})

    source_file = import_csv(session, csv_path, mapping)
    session.commit()

    assert source_file.filename == "export.csv"
    assert source_file.format == "csv"
    assert source_file.row_count == 2
    assert isinstance(source_file.imported_at, datetime.datetime)


def test_import_file__dispatches_csv_to_import_csv(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    mapping = ColumnMapping(fields={"Title": "title"})

    source_file = import_file(session, csv_path, "csv", mapping)

    assert source_file.format == "csv"
    assert source_file.row_count == 1


def test_import_file__unsupported_type_raises(session: Session, tmp_path: Path) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text("TY  - JOUR\n")

    with pytest.raises(ValueError, match="unsupported file type"):
        import_file(session, ris_path, "ris", ColumnMapping())


def _pick(monkeypatch: pytest.MonkeyPatch, path: Path | None) -> None:
    monkeypatch.setattr(
        import_flow.app.native,
        "main_window",
        _FakeWindow((str(path),) if path is not None else None),
    )


def test_render_import_view__initial_state_has_no_file_and_disabled_buttons() -> None:
    panes = shell()

    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    assert view.path is None
    assert view.file_type == "unknown"
    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False
    assert view.stats_button is not None
    assert view.stats_button.enabled is False


def test_render_import_view__selecting_file_updates_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    _pick(monkeypatch, csv_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    asyncio.run(view._select_file())

    assert view.path == csv_path
    # type is still unknown, so no mapping renders yet
    assert view.mapping_screen is None
    outer_column = panes.middle.default_slot.children[0]
    file_row = outer_column.default_slot.children[0]
    assert file_row.default_slot.children[0].text == "export.csv"  # type: ignore[attr-defined]


def test_render_import_view__setting_type_enables_stats_button() -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    view._set_type("csv")

    assert view.file_type == "csv"
    assert view.stats_button is not None
    assert view.stats_button.enabled is True


def test_render_import_view__mapping_renders_inline_and_enables_import_without_confirm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, csv_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)
    asyncio.run(view._select_file())

    assert view.import_button is not None
    assert view.import_button.enabled is False  # type still unknown
    assert view.mapping_screen is None

    view._set_type("csv")

    # mapping table rendered automatically, no "Check Mapping"/confirm click needed
    assert view.mapping_screen is not None
    assert view.import_button.enabled is True


def test_render_import_view__import_reads_live_mapping_edits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Scopus Author ID\nabc123\n")
    _pick(monkeypatch, csv_path)
    calls: list[tuple[Path, str, ColumnMapping]] = []
    view = render_import_view(
        panes.middle, on_import=lambda p, t, m: calls.append((p, t, m))
    )
    asyncio.run(view._select_file())
    view._set_type("csv")
    assert view.mapping_screen is not None

    view.mapping_screen.set_target("Scopus Author ID", "authors")
    view._import()

    assert calls == [
        (csv_path, "csv", ColumnMapping(authors_columns=["Scopus Author ID"]))
    ]


def test_render_import_view__selecting_new_file_rerenders_mapping_from_new_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first_csv = tmp_path / "export.csv"
    first_csv.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, first_csv)
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)
    asyncio.run(view._select_file())
    view._set_type("csv")
    assert view.mapping_screen is not None
    assert [row.header for row in view.mapping_screen.rows] == ["Title"]

    other_csv = tmp_path / "other.csv"
    other_csv.write_text("DOI\n10.1/xyz\n")
    _pick(monkeypatch, other_csv)
    asyncio.run(view._select_file())

    assert view.mapping_screen is not None
    assert [row.header for row in view.mapping_screen.rows] == ["DOI"]
    assert view.import_button is not None
    assert view.import_button.enabled is True


def test_render_import_view__get_stats_click_notifies_not_implemented() -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    view._get_stats()  # must not raise; dry-run logic isn't implemented yet


def test_render_import_view__import_disabled_when_csv_file_cannot_be_decoded(
    tmp_path: Path,
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(b"\x81")  # undefined in both utf-8-sig and cp1252
    view = ImportView(middle=panes.middle, on_import=lambda p, t, m: None)
    view.path = csv_path

    view._set_type("csv")  # must not raise

    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False
