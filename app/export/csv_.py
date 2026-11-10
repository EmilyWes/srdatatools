import csv
from collections.abc import Sequence
from pathlib import Path

from app.export.columns import ExportColumn, ExportRecord, column_value
from app.export.options import ExportOptions


def _cell(value: str, options: ExportOptions) -> str:
    if options.line_breaks == "space":
        return " ".join(value.split("\n")).replace("\r", "")
    return value


def write_csv(
    path: Path,
    columns: Sequence[ExportColumn],
    records: Sequence[ExportRecord],
    options: ExportOptions,
) -> None:
    exported = [column for column in columns if column.name]
    with path.open("w", encoding=options.encoding, newline="") as file:
        writer = csv.writer(file, delimiter=options.delimiter)
        writer.writerow(column.name for column in exported)
        for record in records:
            writer.writerow(
                _cell(column_value(column, record, options), options)
                for column in exported
            )
