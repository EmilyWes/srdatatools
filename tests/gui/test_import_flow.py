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
    show_csv_mapping,
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


def test_show_csv_mapping__renders_mapping_screen_with_file_headers(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")
    panes = shell()
    confirmed: list[tuple[Path, ColumnMapping]] = []

    show_csv_mapping(panes.middle, csv_path, lambda p, m: confirmed.append((p, m)))

    middle_children = panes.middle.default_slot.children
    assert (
        len(middle_children) == 3
    )  # header rows column + delimiter input + Confirm button
    header_rows = middle_children[0].default_slot.children
    assert len(header_rows) == 3  # column header labels row + one row per CSV column
    assert confirmed == []


def test_show_csv_mapping__notifies_when_file_cannot_be_decoded(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(b"\x81")  # undefined in both utf-8-sig and cp1252
    panes = shell()

    show_csv_mapping(panes.middle, csv_path, lambda p, m: None)  # must not raise

    # no mapping screen was rendered; middle still shows the shell's placeholder
    assert panes.middle.default_slot.children[0].text == "Content"  # type: ignore[attr-defined]


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
    assert view.mapping is None
    assert view.check_mapping_button is not None
    assert view.check_mapping_button.enabled is False
    assert view.import_button is not None
    assert view.import_button.enabled is False
    assert view.stats_button is not None
    assert view.stats_button.enabled is False


def test_render_import_view__selecting_file_updates_label_and_enables_check_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    _pick(monkeypatch, csv_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    asyncio.run(view._select_file())

    assert view.path == csv_path
    assert view.check_mapping_button is not None
    assert view.check_mapping_button.enabled is True
    file_row = panes.middle.default_slot.children[0]
    assert file_row.default_slot.children[0].text == "export.csv"  # type: ignore[attr-defined]


def test_render_import_view__setting_type_enables_stats_button() -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    view._set_type("csv")

    assert view.file_type == "csv"
    assert view.stats_button is not None
    assert view.stats_button.enabled is True


def test_render_import_view__import_disabled_until_type_and_mapping_are_set(
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

    view._set_type("csv")
    assert view.import_button.enabled is False  # mapping not confirmed yet

    view._check_mapping()
    mapping_confirm_button = panes.middle.default_slot.children[-1]
    click_listener = next(iter(mapping_confirm_button._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)

    assert view.mapping is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


def test_render_import_view__selecting_new_file_resets_confirmed_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)
    view.path = tmp_path / "export.csv"
    view.mapping = ColumnMapping(fields={"Title": "title"})
    view._set_type("csv")
    assert view.import_button is not None
    assert view.import_button.enabled is True

    other_csv = tmp_path / "other.csv"
    _pick(monkeypatch, other_csv)
    asyncio.run(view._select_file())

    assert view.mapping is None
    assert view.import_button is not None
    assert view.import_button.enabled is False


def test_render_import_view__import_click_calls_on_import_with_args() -> None:
    panes = shell()
    calls: list[tuple[Path, str, ColumnMapping]] = []
    view = render_import_view(
        panes.middle, on_import=lambda p, t, m: calls.append((p, t, m))
    )
    path = Path("export.csv")
    mapping = ColumnMapping(fields={"Title": "title"})
    view.path = path
    view.mapping = mapping
    view._set_type("csv")

    view._import()

    assert calls == [(path, "csv", mapping)]


def test_render_import_view__get_stats_click_notifies_not_implemented() -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m: None)

    view._get_stats()  # must not raise; dry-run logic isn't implemented yet


def test_render_import_view__check_mapping_notifies_when_file_cannot_be_decoded(
    tmp_path: Path,
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(b"\x81")  # undefined in both utf-8-sig and cp1252
    view = ImportView(middle=panes.middle, on_import=lambda p, t, m: None)
    view.path = csv_path
    view.render()

    view._check_mapping()  # must not raise
