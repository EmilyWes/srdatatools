from collections.abc import Sequence
from pathlib import Path

from app.gui.export.mapping import (
    ExportField,
    ExportRecord,
    field_value,
    field_values,
)
from app.gui.export.options import ExportOptions
from app.gui.export.ris_tags import NOTE_TAG

_END_LINE = "ER  - \n\n"


def _lines(
    column: ExportField, record: ExportRecord, options: ExportOptions
) -> list[str]:
    """A line break would end the RIS line, so it is replaced with a space."""
    values = (
        field_values(column, record, options)
        if options.one_line_per_value
        else [field_value(column, record, options)]
    )
    lines = []
    for value in values:
        text = " ".join(value.splitlines())
        if not text:
            continue
        if column.name == NOTE_TAG and column.note_name:
            text = f"{column.note_name}: {text}"
        lines.append(f"{column.name}  - {text}\n")
    return lines


def write_ris(
    path: Path,
    columns: Sequence[ExportField],
    records: Sequence[ExportRecord],
    options: ExportOptions,
) -> None:
    """The columns start with the TY row, as export_fields puts it first."""
    with path.open("w", encoding=options.ris_encoding, newline="\r\n") as file:
        for record in records:
            for column in columns:
                file.writelines(_lines(column, record, options))
            file.write(_END_LINE)
