from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.settings import delete_setting, get_setting, set_setting
from app.gui.format import LabelFormat

_OPTIONS_KEY = "export_options"
_FOLDER_KEY = "export_folder"
_DEFAULT_STEM = "library"


ExportFileType = Literal["csv", "tsv", "xlsx"]


class ExportOptions(BaseModel):
    file_type: ExportFileType = "csv"
    delimiter: Literal[",", ";", "\t"] = ","
    encoding: Literal["utf-8-sig", "utf-8"] = "utf-8"
    label_format: LabelFormat = "numbers"
    line_breaks: Literal["keep", "space"] = "keep"
    # Python's csv module rejects longer fields by default, and so do the tools
    # built on it.
    max_length: int = Field(default=131_072, ge=1)
    # Excel holds at most 32.767 characters per cell.
    excel_max_length: int = Field(default=32_767, ge=1, le=32_767)
    empty_columns: bool = False
    ignored_columns: bool = False
    original_data: bool = False


def load_options(session: Session) -> ExportOptions:
    stored = get_setting(session, _OPTIONS_KEY)
    if stored is None:
        return ExportOptions()
    try:
        return ExportOptions.model_validate_json(stored)
    except ValidationError:
        return ExportOptions()


def save_options(session: Session, options: ExportOptions) -> None:
    set_setting(session, _OPTIONS_KEY, options.model_dump_json())


def reset_options(session: Session) -> None:
    delete_setting(session, _OPTIONS_KEY)


def load_folder(session: Session) -> Path:
    """The last export's folder, or Documents when that folder is gone."""
    stored = get_setting(session, _FOLDER_KEY)
    if stored is not None and Path(stored).is_dir():
        return Path(stored)
    return Path.home() / "Documents"


def save_folder(session: Session, folder: Path) -> None:
    set_setting(session, _FOLDER_KEY, str(folder))


def default_path(folder: Path, file_type: ExportFileType) -> Path:
    """library.csv, or library_1.csv, library_2.csv, ... when it already exists."""
    path = folder / f"{_DEFAULT_STEM}.{file_type}"
    number = 0
    while path.exists():
        number += 1
        path = folder / f"{_DEFAULT_STEM}_{number}.{file_type}"
    return path
