import asyncio
import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.gui import import_flow
from app.gui.import_flow import import_csv, import_file, pick_file, show_csv_mapping
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
    assert len(middle_children) == 4  # 2 header rows + delimiter input + Confirm button
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

    source_file = import_file(session, csv_path, mapping)

    assert source_file.format == "csv"
    assert source_file.row_count == 1


def test_import_file__unsupported_extension_raises(
    session: Session, tmp_path: Path
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text("TY  - JOUR\n")

    with pytest.raises(ValueError, match="unsupported file type"):
        import_file(session, ris_path, ColumnMapping())
