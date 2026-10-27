import datetime
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.parsers.excel import parse_excel_file, read_excel_headers, read_excel_sheets
from app.parsers.mapping import FieldMapping


def _workbook(tmp_path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    for name, rows in sheets.items():
        worksheet = workbook.create_sheet(name)
        for row in rows:
            worksheet.append(row)
    path = tmp_path / "export.xlsx"
    workbook.save(path)
    return path


def _set_cached_values(path: Path, value: str) -> None:
    # openpyxl writes formulas without a cached value; Excel would fill it in on save.
    sheet_xml = "xl/worksheets/sheet1.xml"
    with zipfile.ZipFile(path) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    contents[sheet_xml] = contents[sheet_xml].replace(
        b"<v />", f"<v>{value}</v>".encode()
    )
    with zipfile.ZipFile(path, "w") as target:
        for name, data in contents.items():
            target.writestr(name, data)


def test_parse_excel_file__maps_scalar_fields(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path,
        {"Sheet1": [["Title", "DOI", "Journal"], ["Some Paper", "10.1/xyz", "Nature"]]},
    )
    mapping = FieldMapping(
        targets={"Title": "title", "DOI": "doi", "Journal": "journal"}
    )

    result = parse_excel_file(path, mapping)

    assert len(result.rows) == 1
    assert result.skipped == []
    record = result.rows[0].record
    assert record.title == "Some Paper"
    assert record.doi == "10.1/xyz"
    assert record.journal == "Nature"


def test_parse_excel_file__keeps_raw_fields_including_unmapped_columns(
    tmp_path: Path,
) -> None:
    path = _workbook(
        tmp_path, {"Sheet1": [["Title", "Extra"], ["Some Paper", "unmapped value"]]}
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping)

    assert result.rows[0].raw_fields == {
        "Title": "Some Paper",
        "Extra": "unmapped value",
    }


def test_parse_excel_file__reads_first_sheet_by_default(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path,
        {"Records": [["Title"], ["First"]], "Other": [["Title"], ["Second"]]},
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping)

    assert [row.record.title for row in result.rows] == ["First"]


def test_parse_excel_file__reads_named_sheet(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path,
        {"Records": [["Title"], ["First"]], "Other": [["Title"], ["Second"]]},
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping, sheet="Other")

    assert [row.record.title for row in result.rows] == ["Second"]


def test_parse_excel_file__unknown_sheet_raises(tmp_path: Path) -> None:
    path = _workbook(tmp_path, {"Records": [["Title"], ["First"]]})

    with pytest.raises(ValueError, match="no sheet named 'Missing'"):
        parse_excel_file(path, FieldMapping(), sheet="Missing")


def test_parse_excel_file__converts_cell_values_to_text(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path,
        {
            "Sheet1": [
                ["Int", "Whole", "Float", "Date", "Datetime", "Bool", "Empty"],
                [
                    7,
                    2020.0,
                    1.5,
                    datetime.date(2020, 5, 1),
                    datetime.datetime(2021, 6, 2, 13, 45),
                    True,
                    None,
                ],
            ]
        },
    )

    result = parse_excel_file(path, FieldMapping())

    assert result.rows[0].raw_fields == {
        "Int": "7",
        "Whole": "2020",
        "Float": "1.5",
        "Date": "2020-05-01",
        "Datetime": "2021-06-02",
        "Bool": "TRUE",
        "Empty": "",
    }


def test_parse_excel_file__reads_cached_formula_value(tmp_path: Path) -> None:
    path = _workbook(tmp_path, {"Sheet1": [["Year"], ["=2000+20"]]})
    _set_cached_values(path, "2020")
    mapping = FieldMapping(targets={"Year": "year"})

    result = parse_excel_file(path, mapping)

    assert result.rows[0].raw_fields == {"Year": "2020"}
    publication_date = result.rows[0].record.publication_date
    assert publication_date is not None
    assert publication_date.year == 2020


def test_parse_excel_file__pads_short_row_with_empty_cells(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path, {"Sheet1": [["Title", "DOI", "Journal"], ["Only title"]]}
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping)

    assert result.skipped == []
    assert result.rows[0].raw_fields == {
        "Title": "Only title",
        "DOI": "",
        "Journal": "",
    }


def test_parse_excel_file__skips_row_with_cells_beyond_header(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path,
        {"Sheet1": [["Title"], ["Kept"], ["Dropped", "stray note"]]},
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping)

    assert [row.record.title for row in result.rows] == ["Kept"]
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 3
    assert "more fields" in result.skipped[0].reason


def test_parse_excel_file__drops_trailing_blank_header_cells(tmp_path: Path) -> None:
    path = _workbook(tmp_path, {"Sheet1": [["Title", None, ""], ["Some Paper"]]})

    result = parse_excel_file(path, FieldMapping())

    assert result.rows[0].raw_fields == {"Title": "Some Paper"}


def test_parse_excel_file__ignores_empty_row(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path, {"Sheet1": [["Title", "DOI"], ["First"], [None, None], ["Third"]]}
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping)

    assert [row.record.title for row in result.rows] == ["First", "Third"]
    assert result.skipped == []


def test_parse_excel_file__skips_whitespace_only_row(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path, {"Sheet1": [["Title", "DOI"], ["First", ""], [None, " "], ["Third"]]}
    )
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_excel_file(path, mapping)

    assert [row.record.title for row in result.rows] == ["First", "Third"]
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 3
    assert result.skipped[0].reason == "row is blank"


def test_parse_excel_file__splits_authors_on_delimiter(tmp_path: Path) -> None:
    path = _workbook(tmp_path, {"Sheet1": [["Authors"], ["Jane Smith; John Doe"]]})
    mapping = FieldMapping(targets={"Authors": "authors"})

    result = parse_excel_file(path, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Jane Smith", "John Doe"]


def test_parse_excel_file__non_workbook_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "export.xlsx"
    path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")

    with pytest.raises(ValueError, match="could not read export.xlsx"):
        parse_excel_file(path, FieldMapping())


def test_read_excel_sheets__lists_sheets_in_workbook_order(tmp_path: Path) -> None:
    path = _workbook(tmp_path, {"Records": [], "Notes": [], "Archive": []})

    assert read_excel_sheets(path) == ["Records", "Notes", "Archive"]


def test_read_excel_headers__returns_headers_with_first_non_empty_values(
    tmp_path: Path,
) -> None:
    path = _workbook(
        tmp_path,
        {"Sheet1": [["Title", "DOI"], ["Some Paper", None], ["Other", "10.1/abc"]]},
    )

    samples = read_excel_headers(path).samples

    assert list(samples) == ["Title", "DOI"]
    assert samples == {"Title": "Some Paper", "DOI": "10.1/abc"}


def test_read_excel_headers__counts_rows_and_non_empty_cells_per_column(
    tmp_path: Path,
) -> None:
    path = _workbook(
        tmp_path,
        {"Sheet1": [["Title", "DOI"], ["A", "10.1/a"], [None, None], ["B"]]},
    )

    summary = read_excel_headers(path)

    assert summary.total_rows == 2
    assert summary.filled == {"Title": 2, "DOI": 1}


def test_read_excel_headers__reads_named_sheet(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path, {"Records": [["Title"], ["First"]], "Other": [["DOI"], ["10.1/x"]]}
    )

    assert read_excel_headers(path, sheet="Other").samples == {"DOI": "10.1/x"}


def test_read_excel_headers__empty_sheet_has_no_headers(tmp_path: Path) -> None:
    path = _workbook(tmp_path, {"Sheet1": []})

    summary = read_excel_headers(path)

    assert summary.samples == {}
    assert summary.total_rows == 0
