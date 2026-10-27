import datetime
import logging
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.workbook.workbook import Workbook

from app.parsers.common import (
    FileSummary,
    ParsedRow,
    ParseResult,
    SkippedRow,
    SummaryBuilder,
)
from app.parsers.csv_ import parse_csv_record
from app.parsers.mapping import FieldMapping

logger = logging.getLogger(__name__)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    # Excel stores every number as a float, so years and PMIDs come back as 2020.0.
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _open(path: Path) -> Workbook:
    try:
        return load_workbook(path, read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, KeyError) as exc:
        raise ValueError(f"could not read {path.name} as an Excel workbook") from exc


def _sheet_rows(path: Path, sheet: str | None) -> tuple[list[str], list[list[str]]]:
    workbook = _open(path)
    try:
        names = [worksheet.title for worksheet in workbook.worksheets]
        name = sheet if sheet is not None else names[0]
        if name not in names:
            raise ValueError(f"{path.name} has no sheet named {name!r}")
        rows = [
            [_cell_text(value) for value in row]
            for row in workbook[name].iter_rows(values_only=True)
        ]
    finally:
        workbook.close()
    if not rows:
        return [], []
    headers = rows[0]
    while headers and not headers[-1].strip():
        headers = headers[:-1]
    return headers, rows[1:]


def _is_blank(cells: list[str]) -> bool:
    return all(not cell.strip() for cell in cells)


def _is_empty(cells: list[str]) -> bool:
    return all(not cell for cell in cells)


def read_excel_sheets(path: Path) -> list[str]:
    workbook = _open(path)
    try:
        return [worksheet.title for worksheet in workbook.worksheets]
    finally:
        workbook.close()


def parse_excel_file(
    path: Path, mapping: FieldMapping, sheet: str | None = None
) -> ParseResult:
    headers, data_rows = _sheet_rows(path, sheet)

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []
    for row_number, cells in enumerate(data_rows, start=2):
        # Like blank lines in a CSV: sheets often extend over formatted but empty rows.
        if _is_empty(cells):
            continue
        if not _is_blank(cells[len(headers) :]):
            reason = f"row has more fields than the {len(headers)}-column header"
            skipped.append(SkippedRow(row_number, reason))
            logger.warning("Skipping row %d: %s", row_number, reason)
            continue
        values = cells[: len(headers)] + [""] * (len(headers) - len(cells))
        if _is_blank(values):
            skipped.append(SkippedRow(row_number, "row is blank"))
            logger.warning("Skipping row %d: blank", row_number)
            continue
        rows.append(parse_csv_record(dict(zip(headers, values, strict=True)), mapping))

    return ParseResult(rows=rows, skipped=skipped)


def read_excel_headers(path: Path, sheet: str | None = None) -> FileSummary:
    headers, data_rows = _sheet_rows(path, sheet)
    summary = SummaryBuilder(headers)
    for cells in data_rows:
        if _is_empty(cells):
            continue
        for header, value in zip(headers, cells, strict=False):
            summary.add(header, value)
        summary.end_record()
    return summary.build()
