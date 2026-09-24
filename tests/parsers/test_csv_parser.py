import pytest

from app.parsers.csv_ import ColumnMapping, parse_csv_text


def test_parse_csv_text__maps_scalar_fields() -> None:
    text = "Title,DOI,Journal\nSome Paper,10.1/xyz,Nature\n"
    mapping = ColumnMapping(
        fields={"Title": "title", "DOI": "doi", "Journal": "journal"}
    )

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert result.skipped == []
    record = result.rows[0].record
    assert record.title == "Some Paper"
    assert record.doi == "10.1/xyz"
    assert record.journal == "Nature"


def test_parse_csv_text__keeps_raw_fields_including_unmapped_columns() -> None:
    text = "Title,Extra\nSome Paper,unmapped value\n"
    mapping = ColumnMapping(fields={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].raw_fields == {
        "Title": "Some Paper",
        "Extra": "unmapped value",
    }


def test_parse_csv_text__normalizes_doi_via_record_validator() -> None:
    text = "DOI\nhttps://doi.org/10.1/XYZ\n"
    mapping = ColumnMapping(fields={"DOI": "doi"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.doi == "10.1/xyz"


def test_parse_csv_text__skips_ragged_row_with_missing_fields() -> None:
    text = "Title,DOI,Journal\nOnly title\n"
    mapping = ColumnMapping(fields={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows == []
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 2
    assert "fewer fields" in result.skipped[0].reason


def test_parse_csv_text__skips_ragged_row_with_extra_fields() -> None:
    text = "Title,DOI\nSome Paper,10.1/x,extra,stuff\n"
    mapping = ColumnMapping(fields={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows == []
    assert len(result.skipped) == 1
    assert "more fields" in result.skipped[0].reason


def test_parse_csv_text__skips_fully_blank_row() -> None:
    text = "Title,DOI\nSome Paper,10.1/x\n,\n"
    mapping = ColumnMapping(fields={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "row is blank"


def test_parse_csv_text__imports_row_with_only_unmapped_data() -> None:
    text = "Title,Extra\n,has data\n"
    mapping = ColumnMapping(fields={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert result.rows[0].record.title is None
    assert result.skipped == []


def test_parse_csv_text__sniffs_semicolon_delimiter() -> None:
    text = "Title;DOI\nSome Paper;10.1/x\n"
    mapping = ColumnMapping(fields={"Title": "title", "DOI": "doi"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.title == "Some Paper"
    assert result.rows[0].record.doi == "10.1/x"


def test_column_mapping__rejects_unknown_target_field() -> None:
    with pytest.raises(ValueError):
        ColumnMapping(fields={"Title": "not_a_real_field"})
