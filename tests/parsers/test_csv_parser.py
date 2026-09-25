from pathlib import Path

import pytest

from app.parsers.csv_ import (
    ColumnMapping,
    parse_csv_file,
    parse_csv_text,
    suggest_mapping,
)

CSV_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "csv"


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


def test_parse_csv_text__splits_authors_on_delimiter() -> None:
    text = "Authors\nJane Smith; John Doe\n"
    mapping = ColumnMapping(authors_columns=["Authors"])

    result = parse_csv_text(text, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Jane Smith", "John Doe"]


def test_parse_csv_text__splits_keywords_on_delimiter() -> None:
    text = "Keywords\nmachine learning; nlp\n"
    mapping = ColumnMapping(keywords_columns=["Keywords"])

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.keywords == ["machine learning", "nlp"]


def test_parse_csv_text__uses_custom_list_delimiter() -> None:
    text = "Authors\nJane Smith| John Doe\n"
    mapping = ColumnMapping(authors_columns=["Authors"], list_delimiter="|")

    result = parse_csv_text(text, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Jane Smith", "John Doe"]


def test_parse_csv_text__combines_multiple_author_columns_in_order() -> None:
    text = "First Author,Other Authors\nJane Smith,John Doe; Alice Lee\n"
    mapping = ColumnMapping(authors_columns=["First Author", "Other Authors"])

    result = parse_csv_text(text, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == [
        "Jane Smith",
        "John Doe",
        "Alice Lee",
    ]


def test_parse_csv_text__combines_multiple_keyword_columns_in_order() -> None:
    text = "Author Keywords,Index Keywords\nmachine learning,nlp; llms\n"
    mapping = ColumnMapping(keywords_columns=["Author Keywords", "Index Keywords"])

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.keywords == ["machine learning", "nlp", "llms"]


def test_parse_csv_text__empty_authors_column_gives_empty_list() -> None:
    text = "Title,Authors\nSome Paper,\n"
    mapping = ColumnMapping(fields={"Title": "title"}, authors_columns=["Authors"])

    result = parse_csv_text(text, mapping)

    assert result.skipped == []
    assert result.rows[0].record.authors == []


@pytest.mark.parametrize(
    ("date_value", "expected"),
    [
        ("2020", (2020, None, None)),
        ("2020-05", (2020, 5, None)),
        ("2020-05-14", (2020, 5, 14)),
        ("2020/05/14", (2020, 5, 14)),
    ],
)
def test_parse_csv_text__parses_single_date_column(
    date_value: str, expected: tuple[int, int | None, int | None]
) -> None:
    text = f"Date\n{date_value}\n"
    mapping = ColumnMapping(date_column="Date")

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == expected


def test_parse_csv_text__parses_year_month_day_columns() -> None:
    text = "Year,Month,Day\n2020,5,14\n"
    mapping = ColumnMapping(year_column="Year", month_column="Month", day_column="Day")

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == (2020, 5, 14)


def test_parse_csv_text__accepts_month_abbreviation() -> None:
    text = "Year,Month\n2020,May\n"
    mapping = ColumnMapping(year_column="Year", month_column="Month")

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert date.month == 5


def test_parse_csv_text__drops_day_when_month_missing() -> None:
    text = "Year,Day\n2020,14\n"
    mapping = ColumnMapping(year_column="Year", day_column="Day")

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == (2020, None, None)


def test_parse_csv_text__routes_column_into_other_ids() -> None:
    text = "Title,EID\nSome Paper,2-s2.0-123\n"
    mapping = ColumnMapping(fields={"Title": "title", "EID": "other_ids.eid"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.other_ids == {"eid": "2-s2.0-123"}


def test_parse_csv_text__routes_multiple_columns_into_other_ids() -> None:
    text = "EID,Scopus Author ID\n2-s2.0-123,456\n"
    mapping = ColumnMapping(
        fields={
            "EID": "other_ids.eid",
            "Scopus Author ID": "other_ids.scopus_author_id",
        }
    )

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.other_ids == {
        "eid": "2-s2.0-123",
        "scopus_author_id": "456",
    }


def test_column_mapping__rejects_other_ids_target_without_key() -> None:
    with pytest.raises(ValueError):
        ColumnMapping(fields={"EID": "other_ids."})


def test_column_mapping__rejects_date_column_with_year_column() -> None:
    with pytest.raises(ValueError):
        ColumnMapping(date_column="Date", year_column="Year")


def test_parse_csv_file__falls_back_to_cp1252_on_decode_error() -> None:
    mapping = ColumnMapping(fields={"Title": "title", "Author": "notes"})

    result = parse_csv_file(CSV_FIXTURES_DIR / "cp1252_encoded.csv", mapping)

    assert result.skipped == []
    assert result.rows[0].record.title == "Café Study"
    assert result.rows[0].record.notes == "Müller"


@pytest.mark.parametrize(
    ("header", "expected_target"),
    [
        ("Article Title", "title"),
        ("Source title", "journal"),
        ("Author full names", "authors"),
        ("Author Keywords", "keywords"),
        ("DOI", "doi"),
        ("Document Type", "publication_type"),
        ("Year", "year"),
    ],
)
def test_suggest_mapping__matches_known_vendor_headers(
    header: str, expected_target: str
) -> None:
    suggestions = suggest_mapping([header])

    assert suggestions[header] == expected_target


def test_suggest_mapping__returns_none_for_unrecognized_header() -> None:
    suggestions = suggest_mapping(["Zzzqqqxx123"])

    assert suggestions["Zzzqqqxx123"] is None


def test_column_mapping__rejects_unknown_target_field() -> None:
    with pytest.raises(ValueError):
        ColumnMapping(fields={"Title": "not_a_real_field"})
