from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.settings import get_setting, set_setting
from app.helpers.format import LabelFormat
from app.parsers.profiles.overview import OptionBox, OptionItem

_OPTIONS_KEY = "export_options"
_FOLDER_KEY = "export_folder"
_DEFAULT_STEM = "library"


ExportFileType = Literal["csv", "tsv", "xlsx", "ris"]


class ExportOptions(BaseModel):
    file_type: ExportFileType = "csv"
    delimiter: Literal[",", ";", "\t"] = ","
    encoding: Literal["utf-8-sig", "utf-8"] = "utf-8"
    ris_encoding: Literal["utf-8-sig", "utf-8"] = "utf-8"
    label_format: LabelFormat = "numbers"
    line_breaks: Literal["keep", "space"] = "keep"
    # Python's csv module rejects longer fields by default, and so do the tools
    # built on it.
    max_length: int = Field(default=131_072, ge=1)
    # Excel holds at most 32.767 characters per cell.
    excel_max_length: int = Field(default=32_767, ge=1, le=32_767)
    one_line_per_value: bool = True
    split_pages: bool = True
    cleaned_dates_only: bool = False
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


_DELIMITERS = {",": "Comma", ";": "Semicolon", "\t": "Tab"}
_ENCODINGS = {"utf-8-sig": "UTF-8 with BOM", "utf-8": "UTF-8"}
_LABEL_FORMATS = {"numbers": "Numbers", "words": "Words"}
_LINE_BREAKS = {"keep": "Keep", "space": "Replace with a space"}

_EXCEL_MAX_LENGTH = OptionItem(
    "excel_max_length",
    "Max. length",
    "Longest value written, in characters; longer values are cut. Excel holds at"
    " most 32.767 characters per cell.",
    "number",
)
_RIS_ENCODING = OptionItem(
    "ris_encoding",
    "Encoding",
    "Some RIS readers don't expect a BOM before the first tag.",
    "select",
    choices=_ENCODINGS,
)
_DELIMITER = OptionItem(
    "delimiter",
    "Delimiter",
    "The character between the values in a row.",
    "select",
    choices=_DELIMITERS,
)
_ENCODING = OptionItem(
    "encoding",
    "Encoding",
    "With a BOM, Excel shows accented characters correctly when it opens the file.",
    "select",
    choices=_ENCODINGS,
)
_MAX_LENGTH = OptionItem(
    "max_length",
    "Max. length",
    "Longest value written, in characters; longer values are cut. 131.072 is the"
    " default limit of Python's CSV reader, which many tools use; Excel holds at"
    " most 32.767 characters per cell.",
    "number",
)
_LABEL_FORMAT = OptionItem(
    "label_format",
    "Label values",
    "Numbers writes 1 / 0 / 0.5 / ?, Words writes include / exclude / maybe /"
    " unknown; unlabeled is empty in both.",
    "select",
    choices=_LABEL_FORMATS,
)
_RIS_VALUES = (
    OptionItem(
        "one_line_per_value",
        "One line per value",
        "Writes each author, keyword, ISSN, label, … and each line of the notes on"
        " a tag line of its own, as RIS readers expect. Off joins them on one line"
        " with the row's delimiter.",
        "checkbox",
    ),
    OptionItem(
        "split_pages",
        "Split pages into SP / EP",
        "Writes the start page to SP and the end page to EP. Off writes the whole"
        " range to SP.",
        "checkbox",
    ),
    OptionItem(
        "cleaned_dates_only",
        "Only export cleaned dates",
        "Writes only dates Cleaning turned into YYYY/MM/DD to DA. Off writes other"
        " dates as stored.",
        "checkbox",
    ),
)
_COLUMN_SELECTION = OptionBox(
    "Column selection",
    (
        OptionItem(
            "empty_columns",
            "Export empty columns",
            "Adds the columns that none of the exported records has a value for.",
            "checkbox",
        ),
        OptionItem(
            "ignored_columns",
            "Export ignored input columns",
            "Adds a row for each input column or tag that was set to ignore at"
            " import, with the value as it was imported.",
            "checkbox",
            disabled_by="original_data",
        ),
        OptionItem(
            "original_data",
            "Export original data",
            "Adds a row for every input column or tag, with the value as it was"
            " imported.",
            "checkbox",
        ),
    ),
)


def _line_breaks(file_type: ExportFileType) -> OptionItem:
    where = "in the cell" if file_type == "xlsx" else "within quotes"
    return OptionItem(
        "line_breaks",
        "Line breaks",
        f"Line breaks inside a value (e.g. an abstract) are kept {where}, or"
        " replaced with a space.",
        "select",
        wide=True,
        choices=_LINE_BREAKS,
    )


def export_boxes(file_type: ExportFileType) -> list[OptionBox]:
    file_items: tuple[OptionItem, ...]
    values_items: tuple[OptionItem, ...]
    if file_type == "ris":
        file_items = (_RIS_ENCODING,)
        values_items = (_LABEL_FORMAT, *_RIS_VALUES)
    else:
        if file_type == "xlsx":
            file_items = (_EXCEL_MAX_LENGTH,)
        else:
            file_items = (_DELIMITER, _ENCODING, _MAX_LENGTH)
        values_items = (_LABEL_FORMAT, _line_breaks(file_type))
    return [
        OptionBox("File", file_items),
        OptionBox("Values", values_items),
        _COLUMN_SELECTION,
    ]
