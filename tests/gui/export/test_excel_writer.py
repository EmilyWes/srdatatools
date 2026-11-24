from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.gui.export.columns import ExportColumn, ExportRecord, export_columns
from app.gui.export.excel import write_excel
from app.gui.export.options import ExportOptions
from app.models.record import Record
from app.parsers.csv_ import suggest_mapping
from app.parsers.excel import parse_excel_file

_RECORDS = [
    ExportRecord(
        id=1,
        record=Record(
            title="Deep learning, a review",
            author_names=["LeCun, Yann; Bengio, Yoshua"],
            abstract="First line.\nSecond line.",
            publication_date="2015/05/",
            volume="521",
            doi="10.1038/nature14539",
            keywords={"": ["deep learning"], "MeSH": ["Humans"]},
        ),
    ),
    ExportRecord(
        id=2,
        record=Record(
            title="Gradient-based learning applied to document recognition",
            author_names=["LeCun, Yann"],
            publication_date="1998//",
            volume="086",
            doi="10.1109/5.726791",
        ),
    ),
]


def _columns(
    names: dict[str, str], records: list[ExportRecord], options: ExportOptions
) -> list[ExportColumn]:
    columns = [c for c in export_columns(records, options) if c.key in names]
    for column in columns:
        column.name = names[column.key]
    return columns


def _write(
    tmp_path: Path,
    names: dict[str, str],
    options: ExportOptions | None = None,
    records: list[ExportRecord] | None = None,
) -> Worksheet:
    options = options or ExportOptions(file_type="xlsx")
    records = records if records is not None else _RECORDS
    path = tmp_path / "library.xlsx"
    write_excel(path, _columns(names, records, options), records, options)
    return load_workbook(path)["Records"]


def _rows(sheet: Worksheet) -> list[list[object]]:
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def _titled(*titles: str) -> list[ExportRecord]:
    return [
        ExportRecord(id=i, record=Record(title=title))
        for i, title in enumerate(titles, start=1)
    ]


def test_write_excel__given_columns_in_order(tmp_path: Path) -> None:
    sheet = _write(tmp_path, {"title": "Title", "doi": "DOI"})

    assert _rows(sheet) == [
        ["Title", "DOI"],
        ["Deep learning, a review", "10.1038/nature14539"],
        [
            "Gradient-based learning applied to document recognition",
            "10.1109/5.726791",
        ],
    ]


def test_write_excel__only_sheet_is_records(tmp_path: Path) -> None:
    _write(tmp_path, {"doi": "DOI"})

    assert load_workbook(tmp_path / "library.xlsx").sheetnames == ["Records"]


def test_write_excel__header_frozen_with_autofilter(tmp_path: Path) -> None:
    sheet = _write(tmp_path, {"title": "Title", "doi": "DOI"})

    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:B3"


def test_write_excel__empty_name_writes_empty_header(tmp_path: Path) -> None:
    sheet = _write(tmp_path, {"title": "", "doi": "DOI"})

    assert _rows(sheet)[0] == [None, "DOI"]


def test_write_excel__whole_numbers_as_numbers(tmp_path: Path) -> None:
    sheet = _write(tmp_path, {"record_id": "Record ID", "volume": "Volume"})

    assert _rows(sheet)[1:] == [[1, 521], [2, "086"]]


def test_write_excel__numbers_rules(tmp_path: Path) -> None:
    records = _titled(
        "0", "-12", "123456789012345", "1234567890123456", "1.5", "1e5", " 12", "-0"
    )

    sheet = _write(tmp_path, {"title": "Title"}, records=records)

    assert [row[0] for row in _rows(sheet)[1:]] == [
        0,
        -12,
        123456789012345,
        "1234567890123456",
        "1.5",
        "1e5",
        " 12",
        "-0",
    ]


def test_write_excel__equals_sign_written_as_text(tmp_path: Path) -> None:
    sheet = _write(tmp_path, {"title": "Title"}, records=_titled("=1+1"))

    assert sheet["A2"].value == "=1+1"
    assert sheet["A2"].data_type == "s"


def test_write_excel__line_breaks_kept_by_default(tmp_path: Path) -> None:
    sheet = _write(tmp_path, {"abstract": "Abstract"})

    assert sheet["A2"].value == "First line.\nSecond line."


def test_write_excel__line_breaks_replaced_with_space(tmp_path: Path) -> None:
    options = ExportOptions(file_type="xlsx", line_breaks="space")

    sheet = _write(tmp_path, {"abstract": "Abstract"}, options)

    assert sheet["A2"].value == "First line. Second line."


def test_write_excel__cuts_values_over_the_excel_maximum_length(
    tmp_path: Path,
) -> None:
    options = ExportOptions(file_type="xlsx", max_length=4, excel_max_length=8)
    path = tmp_path / "library.xlsx"

    cut, removed = write_excel(
        path, _columns({"title": "Title"}, _RECORDS, options), _RECORDS, options
    )

    sheet = load_workbook(path)["Records"]
    assert [row[0] for row in _rows(sheet)[1:]] == ["Deep lea", "Gradient"]
    assert (cut, removed) == (2, 0)


def test_write_excel__strips_and_counts_control_characters(tmp_path: Path) -> None:
    options = ExportOptions(file_type="xlsx")
    records = _titled("Bell\x07 and\x0b tab\tline\nend", "\x01", "clean")
    path = tmp_path / "library.xlsx"

    cut, removed = write_excel(
        path, _columns({"title": "Ti\x02tle"}, records, options), records, options
    )

    sheet = load_workbook(path)["Records"]
    assert _rows(sheet) == [
        ["Title"],
        ["Bell and tab\tline\nend"],
        [None],
        ["clean"],
    ]
    assert (cut, removed) == (0, 2)


def test_write_excel__round_trips_through_the_excel_importer(tmp_path: Path) -> None:
    options = ExportOptions(file_type="xlsx")
    path = tmp_path / "library.xlsx"

    write_excel(path, export_columns(_RECORDS, options), _RECORDS, options)

    headers = [str(cell) for cell in _rows(load_workbook(path)["Records"])[0]]
    result = parse_excel_file(path, suggest_mapping(headers))
    assert not result.skipped
    first = result.rows[0].record
    assert first.title == "Deep learning, a review"
    assert first.author_names == ["LeCun, Yann; Bengio, Yoshua"]
    assert first.doi == "10.1038/nature14539"
    assert first.publication_date == "2015/05/"
    assert first.volume == "521"
    assert first.keywords[""] == ["deep learning"]
    assert result.rows[1].record.volume == "086"
