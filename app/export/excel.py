import re
from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.utils import get_column_letter
from openpyxl.worksheet._write_only import WriteOnlyWorksheet

from app.export.columns import ExportColumn, ExportRecord, column_value
from app.export.csv_ import line_breaks
from app.export.options import ExportOptions

_SHEET_NAME = "Records"
# Excel keeps 15 significant digits, so longer numbers would be rounded.
_WHOLE_NUMBER = re.compile(r"0|-?[1-9]\d{0,14}")


def _text_cell(sheet: WriteOnlyWorksheet, value: str) -> Cell:
    cell = WriteOnlyCell(sheet, value=value)
    # openpyxl would otherwise store a value starting with "=" as a formula.
    cell.data_type = "s"
    return cell


def _cell(sheet: WriteOnlyWorksheet, value: str) -> Cell | int | None:
    if not value:
        return None
    if _WHOLE_NUMBER.fullmatch(value):
        return int(value)
    return _text_cell(sheet, value)


def write_excel(
    path: Path,
    columns: Sequence[ExportColumn],
    records: Sequence[ExportRecord],
    options: ExportOptions,
) -> tuple[int, int]:
    """Returns how many values were cut to the maximum length and how many had
    characters removed that Excel can't store."""
    cut = removed = 0
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(_SHEET_NAME)
    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(columns))
    sheet.auto_filter.ref = f"A1:{last_column}{len(records) + 1}"
    sheet.append(
        [_text_cell(sheet, ILLEGAL_CHARACTERS_RE.sub("", c.name)) for c in columns]
    )
    for record in records:
        row: list[Cell | int | None] = []
        for column in columns:
            value = line_breaks(column_value(column, record, options), options)
            if len(value) > options.excel_max_length:
                value = value[: options.excel_max_length]
                cut += 1
            stripped = ILLEGAL_CHARACTERS_RE.sub("", value)
            if stripped != value:
                removed += 1
            row.append(_cell(sheet, stripped))
        sheet.append(row)
    workbook.save(path)
    return cut, removed
