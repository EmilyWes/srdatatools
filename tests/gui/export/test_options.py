from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.db.settings import set_setting
from app.gui.export.options import (
    ExportFileType,
    ExportOptions,
    default_path,
    export_boxes,
    load_folder,
    load_options,
    save_folder,
    save_options,
)
from app.helpers.options_overview import OptionItem


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_load_folder__documents_when_unset(session: Session) -> None:
    assert load_folder(session) == Path.home() / "Documents"


def test_save_folder__round_trips(session: Session, tmp_path: Path) -> None:
    save_folder(session, tmp_path)
    session.commit()

    assert load_folder(session) == tmp_path


def test_load_folder__documents_when_saved_folder_is_gone(
    session: Session, tmp_path: Path
) -> None:
    save_folder(session, tmp_path / "gone")
    session.commit()

    assert load_folder(session) == Path.home() / "Documents"


def test_default_path__library_when_free(tmp_path: Path) -> None:
    assert default_path(tmp_path, "csv") == tmp_path / "library.csv"
    assert default_path(tmp_path, "tsv") == tmp_path / "library.tsv"
    assert default_path(tmp_path, "xlsx") == tmp_path / "library.xlsx"
    assert default_path(tmp_path, "ris") == tmp_path / "library.ris"


def test_default_path__numbers_past_existing_files(tmp_path: Path) -> None:
    (tmp_path / "library.csv").touch()
    (tmp_path / "library_1.csv").touch()

    assert default_path(tmp_path, "csv") == tmp_path / "library_2.csv"
    assert default_path(tmp_path, "tsv") == tmp_path / "library.tsv"


def test_load_options__defaults_when_unset(session: Session) -> None:
    assert load_options(session) == ExportOptions()


def test_save_options__round_trips(session: Session) -> None:
    options = ExportOptions(
        file_type="xlsx",
        delimiter="\t",
        encoding="utf-8",
        excel_max_length=1_000,
        original_data=True,
    )

    save_options(session, options)
    session.commit()

    assert load_options(session) == options


def test_load_options__defaults_when_stored_value_is_invalid(session: Session) -> None:
    set_setting(session, "export_options", '{"delimiter": "|"}')
    session.commit()

    assert load_options(session) == ExportOptions()


def test_load_options__defaults_to_pythons_csv_field_limit(session: Session) -> None:
    assert load_options(session).max_length == 131_072


def test_load_options__excel_length_defaults_to_excels_cell_limit(
    session: Session,
) -> None:
    assert load_options(session).excel_max_length == 32_767


def test_load_options__defaults_when_excel_length_over_cell_limit(
    session: Session,
) -> None:
    set_setting(session, "export_options", '{"excel_max_length": 32768}')
    session.commit()

    assert load_options(session) == ExportOptions()


def _keys(file_type: ExportFileType) -> dict[str, list[str]]:
    return {
        box.title: [item.key for item in box.items if isinstance(item, OptionItem)]
        for box in export_boxes(file_type)
    }


def test_export_boxes__csv_and_tsv() -> None:
    for file_type in ("csv", "tsv"):
        assert _keys(file_type) == {
            "File": ["delimiter", "encoding", "max_length"],
            "Values": ["label_format", "line_breaks"],
            "Column selection": ["empty_columns", "ignored_columns", "original_data"],
        }


def test_export_boxes__excel() -> None:
    keys = _keys("xlsx")

    assert keys["File"] == ["excel_max_length"]
    assert keys["Values"] == ["label_format", "line_breaks"]


def test_export_boxes__ris() -> None:
    keys = _keys("ris")

    assert keys["File"] == ["ris_encoding"]
    assert keys["Values"] == [
        "label_format",
        "one_line_per_value",
        "split_pages",
        "cleaned_dates_only",
    ]


def test_export_boxes__line_breaks_hover_per_file_type() -> None:
    def hover(file_type: ExportFileType) -> str:
        [values] = [box for box in export_boxes(file_type) if box.title == "Values"]
        [item] = [i for i in values.items if getattr(i, "key", "") == "line_breaks"]
        assert isinstance(item, OptionItem)
        return item.hover

    assert "in the cell" in hover("xlsx")
    assert "within quotes" in hover("csv")


def test_export_boxes__every_key_is_an_option() -> None:
    for file_type in ("csv", "tsv", "xlsx", "ris"):
        for box in export_boxes(file_type):
            for item in box.items:
                assert isinstance(item, OptionItem)
                assert item.key in ExportOptions.model_fields
