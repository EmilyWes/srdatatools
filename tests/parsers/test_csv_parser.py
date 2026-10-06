from pathlib import Path

import pytest

from app.parsers.csv_ import (
    parse_csv_file,
    parse_csv_text,
    read_csv_headers,
    suggest_mapping,
)
from app.parsers.mapping import FieldMapping

CSV_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "csv"


def test_parse_csv_text__maps_scalar_fields() -> None:
    text = "Title,DOI,Journal\nSome Paper,10.1/xyz,Nature\n"
    mapping = FieldMapping(
        targets={"Title": "title", "DOI": "doi", "Journal": "journal"}
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
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].raw_fields == {
        "Title": "Some Paper",
        "Extra": "unmapped value",
    }


def test_parse_csv_text__normalizes_doi_via_record_validator() -> None:
    text = "DOI\nhttps://doi.org/10.1/XYZ\n"
    mapping = FieldMapping(targets={"DOI": "doi"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.doi == "10.1/xyz"


def test_parse_csv_text__skips_ragged_row_with_missing_fields() -> None:
    text = "Title,DOI,Journal\nOnly title\n"
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows == []
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 2
    assert "fewer fields" in result.skipped[0].reason


def test_parse_csv_text__skips_ragged_row_with_extra_fields() -> None:
    text = "Title,DOI\nSome Paper,10.1/x,extra,stuff\n"
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows == []
    assert len(result.skipped) == 1
    assert "more fields" in result.skipped[0].reason


def test_parse_csv_text__skips_fully_blank_row() -> None:
    text = "Title,DOI\nSome Paper,10.1/x\n,\n"
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "row is blank"


def test_parse_csv_text__imports_row_with_only_unmapped_data() -> None:
    text = "Title,Extra\n,has data\n"
    mapping = FieldMapping(targets={"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert result.rows[0].record.title is None
    assert result.skipped == []


def test_parse_csv_text__sniffs_semicolon_delimiter() -> None:
    text = "Title;DOI\nSome Paper;10.1/x\n"
    mapping = FieldMapping(targets={"Title": "title", "DOI": "doi"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.title == "Some Paper"
    assert result.rows[0].record.doi == "10.1/x"


def test_parse_csv_text__splits_authors_on_delimiter() -> None:
    text = "Authors\nJane Smith; John Doe\n"
    mapping = FieldMapping(targets={"Authors": "authors"})

    result = parse_csv_text(text, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Jane Smith", "John Doe"]


def test_parse_csv_text__splits_keywords_on_delimiter() -> None:
    text = "Keywords\nmachine learning; nlp\n"
    mapping = FieldMapping(targets={"Keywords": "keywords"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.keywords == ["machine learning", "nlp"]


def test_parse_csv_text__uses_custom_list_delimiter() -> None:
    text = "Authors\nJane Smith| John Doe\n"
    mapping = FieldMapping(targets={"Authors": "authors"}, list_delimiter="|")

    result = parse_csv_text(text, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Jane Smith", "John Doe"]


def test_parse_csv_text__combines_multiple_author_columns_in_order() -> None:
    text = "First Author,Other Authors\nJane Smith,John Doe; Alice Lee\n"
    mapping = FieldMapping(
        targets={"First Author": "authors", "Other Authors": "authors"}
    )

    result = parse_csv_text(text, mapping)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == [
        "Jane Smith",
        "John Doe",
        "Alice Lee",
    ]


def test_parse_csv_text__combines_multiple_keyword_columns_in_order() -> None:
    text = "Author Keywords,Index Keywords\nmachine learning,nlp; llms\n"
    mapping = FieldMapping(
        targets={"Author Keywords": "keywords", "Index Keywords": "keywords"}
    )

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.keywords == ["machine learning", "nlp", "llms"]


def test_parse_csv_text__empty_authors_column_gives_empty_list() -> None:
    text = "Title,Authors\nSome Paper,\n"
    mapping = FieldMapping(targets={"Title": "title", "Authors": "authors"})

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
    mapping = FieldMapping(targets={"Date": "date"})

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == expected


def test_parse_csv_text__parses_year_month_day_columns() -> None:
    text = "Year,Month,Day\n2020,5,14\n"
    mapping = FieldMapping(targets={"Year": "year", "Month": "month", "Day": "day"})

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == (2020, 5, 14)


def test_parse_csv_text__accepts_month_abbreviation() -> None:
    text = "Year,Month\n2020,May\n"
    mapping = FieldMapping(targets={"Year": "year", "Month": "month"})

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert date.month == 5


def test_parse_csv_text__drops_day_when_month_missing() -> None:
    text = "Year,Day\n2020,14\n"
    mapping = FieldMapping(targets={"Year": "year", "Day": "day"})

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == (2020, None, None)


def test_parse_csv_text__routes_column_into_other_ids() -> None:
    text = "Title,EID\nSome Paper,2-s2.0-123\n"
    mapping = FieldMapping(targets={"Title": "title", "EID": "other_ids.eid"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.other_ids == {"eid": "2-s2.0-123"}


def test_parse_csv_text__routes_multiple_columns_into_other_ids() -> None:
    text = "EID,Scopus Author ID\n2-s2.0-123,456\n"
    mapping = FieldMapping(
        targets={
            "EID": "other_ids.eid",
            "Scopus Author ID": "other_ids.scopus_author_id",
        }
    )

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.other_ids == {
        "eid": "2-s2.0-123",
        "scopus_author_id": "456",
    }


def _ymd(text: str, mapping: FieldMapping) -> tuple[int | None, ...]:
    date = parse_csv_text(text, mapping).rows[0].record.publication_date
    assert date is not None
    return (date.year, date.month, date.day)


def test_parse_csv_text__ymd_overrides_date_on_conflict() -> None:
    text = "Year,Month,Day,Created\n2019,3,7,2020-05-14\n"
    mapping = FieldMapping(
        targets={"Year": "year", "Month": "month", "Day": "day", "Created": "date"}
    )

    assert _ymd(text, mapping) == (2019, 3, 7)


def test_parse_csv_text__fills_missing_parts_from_date_column() -> None:
    text = "Year,Created\n2020,2020-05-14\n"
    mapping = FieldMapping(targets={"Year": "year", "Created": "date"})

    assert _ymd(text, mapping) == (2020, 5, 14)


def test_parse_csv_text__falls_back_to_date_when_ymd_cells_blank() -> None:
    text = "Year,Created\n,2020-05-14\n"
    mapping = FieldMapping(targets={"Year": "year", "Created": "date"})

    assert _ymd(text, mapping) == (2020, 5, 14)


def test_parse_csv_text__unparseable_date_column_keeps_ymd() -> None:
    text = "Year,Created\n2020,sometime in May\n"
    mapping = FieldMapping(targets={"Year": "year", "Created": "date"})

    assert _ymd(text, mapping) == (2020, None, None)


def test_parse_csv_text__maps_publication_year_and_create_date_together() -> None:
    text = "Publication Year,Create Date\n2018,2020-05-14\n"
    mapping = FieldMapping(targets={"Publication Year": "year", "Create Date": "date"})

    assert _ymd(text, mapping) == (2018, 5, 14)


def test_parse_csv_file__falls_back_to_cp1252_on_decode_error() -> None:
    mapping = FieldMapping(targets={"Title": "title", "Author": "notes"})

    result = parse_csv_file(CSV_FIXTURES_DIR / "cp1252_encoded.csv", mapping)

    assert result.skipped == []
    assert result.rows[0].record.title == "Café Study"
    assert result.rows[0].record.notes == "Müller"


def test_read_csv_headers__returns_headers_with_first_row_values(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text(
        "Title,DOI,Journal\nSome Paper,10.1/xyz,Nature\nOther,10.1/abc,Science\n"
    )

    samples = read_csv_headers(csv_path).samples

    assert list(samples) == ["Title", "DOI", "Journal"]
    assert samples == {"Title": "Some Paper", "DOI": "10.1/xyz", "Journal": "Nature"}


def test_read_csv_headers__skips_blank_cells_to_first_non_empty_value(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nA,\nB,  \nC,10.1/xyz\n")

    assert read_csv_headers(csv_path).samples == {"Title": "A", "DOI": "10.1/xyz"}


def test_read_csv_headers__column_empty_in_every_row_has_empty_sample(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,Notes\nA,\nB,\n")

    assert read_csv_headers(csv_path).samples == {"Title": "A", "Notes": ""}


def test_read_csv_headers__header_only_file_has_empty_samples(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\n")

    assert read_csv_headers(csv_path).samples == {"Title": "", "DOI": ""}


def test_read_csv_headers__short_row_leaves_missing_cells_for_later_rows(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nA\nB,10.1/xyz\n")

    assert read_csv_headers(csv_path).samples == {"Title": "A", "DOI": "10.1/xyz"}


def test_read_csv_headers__empty_file_returns_empty_dict(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("")

    assert read_csv_headers(csv_path).samples == {}


def test_read_csv_headers__decodes_cp1252_file() -> None:
    samples = read_csv_headers(CSV_FIXTURES_DIR / "cp1252_encoded.csv").samples

    assert samples == {"Title": "Café Study", "Author": "Müller"}


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
        ("Page start", "page_start"),
        ("Page end", "page_end"),
        ("PMID", "pmid"),
        ("PMCID", "other_ids.pmcid"),
        ("PMC ID", "other_ids.pmc_id"),
    ],
)
def test_suggest_mapping__matches_known_vendor_headers(
    header: str, expected_target: str
) -> None:
    suggestions = suggest_mapping([header])

    assert suggestions.targets == {header: expected_target}


@pytest.mark.parametrize(
    ("header", "expected_target"),
    [
        ("Scopus Author ID", "other_ids.scopus_author_id"),
        ("Custom ID", "other_ids.custom_id"),
        ("Zotero ID", "other_ids.zotero_id"),
    ],
)
def test_suggest_mapping__unmatched_id_header_falls_back_to_other_ids(
    header: str, expected_target: str
) -> None:
    suggestions = suggest_mapping([header])

    assert suggestions.targets == {header: expected_target}


@pytest.mark.parametrize("header", ["Valid", "Wide", "Identifier", "Provider"])
def test_suggest_mapping__non_id_words_containing_id_stay_unmapped(
    header: str,
) -> None:
    suggestions = suggest_mapping([header])

    assert suggestions.targets == {}


def test_suggest_mapping__leaves_unrecognized_header_out() -> None:
    suggestions = suggest_mapping(["Zzzqqqxx123"])

    assert suggestions.targets == {}


def test_suggest_mapping__keeps_only_first_column_per_date_part() -> None:
    suggestions = suggest_mapping(["Year", "Publication Year", "Date"])

    assert suggestions.targets == {"Year": "year", "Date": "date"}


def test_read_csv_headers__counts_rows_and_non_empty_cells_per_column(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nA,\nB,  \nC,10.1/xyz\n")

    summary = read_csv_headers(csv_path)

    assert summary.total_rows == 3
    assert summary.filled == {"Title": 3, "DOI": 1}


def test_read_csv_headers__short_row_counts_as_row_with_missing_cells_empty(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nA\nB,10.1/xyz\n")

    summary = read_csv_headers(csv_path)

    assert summary.total_rows == 2
    assert summary.filled == {"Title": 2, "DOI": 1}


def test_read_csv_headers__blank_lines_are_not_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nA\n\nB\n")

    assert read_csv_headers(csv_path).total_rows == 2


def test_read_csv_headers__header_only_and_empty_files_have_zero_rows(
    tmp_path: Path,
) -> None:
    header_only = tmp_path / "header_only.csv"
    header_only.write_text("Title,DOI\n")
    empty = tmp_path / "empty.csv"
    empty.write_text("")

    assert read_csv_headers(header_only).filled == {"Title": 0, "DOI": 0}
    assert read_csv_headers(header_only).total_rows == 0
    assert read_csv_headers(empty).total_rows == 0
