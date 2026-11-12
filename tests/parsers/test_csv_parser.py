from pathlib import Path

import pytest

from app.models.record import Record
from app.parsers import csv_
from app.parsers.common import SkippedRow
from app.parsers.csv_ import (
    parse_csv_file,
    parse_csv_record,
    parse_csv_text,
    read_csv_headers,
    suggest_mapping,
)
from app.parsers.mapping import (
    AuthorsRow,
    DateRow,
    FieldMapping,
    IssnIsbnRow,
    KeywordsRow,
    OtherIdRow,
    PagesRow,
    RowMapping,
    ScalarRow,
    Suggest,
)
from app.parsers.quirks import ParseSettings
from tests.mappings import mapping_of, targets_of

CSV_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "general"


def test_parse_csv_text__maps_scalar_fields() -> None:
    text = "Title,DOI,Journal\nSome Paper,10.1/xyz,Nature\n"
    mapping = mapping_of({"Title": "title", "DOI": "doi", "Journal": "journal"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert result.skipped == []
    record = result.rows[0].record
    assert record.title == "Some Paper"
    assert record.doi == "10.1/xyz"
    assert record.journal == "Nature"


def test_parse_csv_text__keeps_raw_fields_including_unmapped_columns() -> None:
    text = "Title,Extra\nSome Paper,unmapped value\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].raw_fields == {
        "Title": "Some Paper",
        "Extra": "unmapped value",
    }


def test_parse_csv_text__normalizes_doi_via_record_validator() -> None:
    text = "DOI\nhttps://doi.org/10.1/XYZ\n"
    mapping = mapping_of({"DOI": "doi"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.doi == "10.1/xyz"


def test_parse_csv_text__skips_ragged_row_with_missing_fields() -> None:
    text = "Title,DOI,Journal\nOnly title\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows == []
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 2
    assert "fewer fields" in result.skipped[0].reason


def test_parse_csv_text__skips_ragged_row_with_extra_fields() -> None:
    text = "Title,DOI\nSome Paper,10.1/x,extra,stuff\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert result.rows == []
    assert len(result.skipped) == 1
    assert "more fields" in result.skipped[0].reason


def test_parse_csv_text__skips_fully_blank_row() -> None:
    text = "Title,DOI\nSome Paper,10.1/x\n,\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == "row is blank"


def test_parse_csv_text__reads_cell_over_default_csv_limit() -> None:
    abstract = "x" * 200_000
    text = f"Title,Abstract\nSome Paper,{abstract}\n"
    mapping = mapping_of({"Title": "title", "Abstract": "abstract"})

    result = parse_csv_text(text, mapping)

    assert result.skipped == []
    assert result.rows[0].record.abstract == abstract


def test_parse_csv_text__skips_row_with_cell_over_limit() -> None:
    text = f"Title,Abstract\nA,{'x' * 1_000_001}\nB,short\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert [row.record.title for row in result.rows] == ["B"]
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 2
    assert "field limit" in result.skipped[0].reason


def test_parse_csv_text__imports_row_with_only_unmapped_data() -> None:
    text = "Title,Extra\n,has data\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping)

    assert len(result.rows) == 1
    assert result.rows[0].record.title is None
    assert result.skipped == []


def test_parse_csv_text__sniffs_semicolon_delimiter() -> None:
    text = "Title;DOI\nSome Paper;10.1/x\n"
    mapping = mapping_of({"Title": "title", "DOI": "doi"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.title == "Some Paper"
    assert result.rows[0].record.doi == "10.1/x"


def test_parse_csv_text__doubled_quote_after_sniff_sample_is_an_escape() -> None:
    plain_rows = "".join(
        f'"Paper {n}","Plain abstract, no quotes"\n' for n in range(80)
    )
    text = f'"Title","Abstract"\n{plain_rows}"Late","The ""deep-water"" model, again"\n'
    mapping = mapping_of({"Title": "title", "Abstract": "abstract"})

    result = parse_csv_text(text, mapping)

    assert result.skipped == []
    assert result.rows[-1].record.abstract == 'The "deep-water" model, again'


def test_parse_csv_text__keeps_authors_as_in_the_file() -> None:
    text = "Authors\nJane Smith; John Doe\n"
    mapping = mapping_of({"Authors": "authors"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.author_names == "Jane Smith; John Doe"


def test_parse_csv_text__splits_keywords_on_delimiter() -> None:
    text = "Keywords\nmachine learning; nlp\n"
    mapping = mapping_of({"Keywords": "keywords"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.keywords == ["machine learning", "nlp"]


def test_parse_csv_text__keeps_author_id_column_unsplit() -> None:
    text = "IDs\n1| 2\n"
    mapping = mapping_of({"IDs": Suggest("authors", {"role": "ids", "id_key": "x"})})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.author_ids == "x:[1| 2]"


def test_parse_csv_text__first_non_empty_name_column_sets_the_authors() -> None:
    text = "First Author,Other Authors\n,John Doe; Alice Lee\n"
    mapping = mapping_of({"First Author": "authors", "Other Authors": "authors"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.author_names == "John Doe; Alice Lee"


def test_parse_csv_text__combines_multiple_keyword_columns_in_order() -> None:
    text = "Author Keywords,Index Keywords\nmachine learning,nlp; llms\n"
    mapping = mapping_of({"Author Keywords": "keywords", "Index Keywords": "keywords"})

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.keywords == ["machine learning", "nlp", "llms"]


def test_parse_csv_text__empty_authors_column_gives_no_authors() -> None:
    text = "Title,Authors\nSome Paper,\n"
    mapping = mapping_of({"Title": "title", "Authors": "authors"})

    result = parse_csv_text(text, mapping)

    assert result.skipped == []
    assert result.rows[0].record.author_names is None


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
    mapping = mapping_of({"Date": "date"})

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == expected


def test_parse_csv_text__parses_year_month_day_columns() -> None:
    text = "Year,Month,Day\n2020,5,14\n"
    mapping = mapping_of(
        {
            "Year": Suggest("date", {"part": "year"}),
            "Month": Suggest("date", {"part": "month"}),
            "Day": Suggest("date", {"part": "day"}),
        }
    )

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == (2020, 5, 14)


def test_parse_csv_text__accepts_month_abbreviation() -> None:
    text = "Year,Month\n2020,May\n"
    mapping = mapping_of(
        {
            "Year": Suggest("date", {"part": "year"}),
            "Month": Suggest("date", {"part": "month"}),
        }
    )

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert date.month == 5


def test_parse_csv_text__drops_day_when_month_missing() -> None:
    text = "Year,Day\n2020,14\n"
    mapping = mapping_of(
        {
            "Year": Suggest("date", {"part": "year"}),
            "Day": Suggest("date", {"part": "day"}),
        }
    )

    result = parse_csv_text(text, mapping)

    date = result.rows[0].record.publication_date
    assert date is not None
    assert (date.year, date.month, date.day) == (2020, None, None)


def test_parse_csv_text__routes_column_into_other_ids() -> None:
    text = "Title,EID\nSome Paper,2-s2.0-123\n"
    mapping = mapping_of(
        {"Title": "title", "EID": Suggest("other_ids", {"key": "eid"})}
    )

    result = parse_csv_text(text, mapping)

    assert result.rows[0].record.other_ids == {"eid": "2-s2.0-123"}


def test_parse_csv_text__routes_multiple_columns_into_other_ids() -> None:
    text = "EID,Scopus Author ID\n2-s2.0-123,456\n"
    mapping = mapping_of(
        {
            "EID": Suggest("other_ids", {"key": "eid"}),
            "Scopus Author ID": Suggest("other_ids", {"key": "scopus_author_id"}),
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
    mapping = mapping_of(
        {
            "Year": Suggest("date", {"part": "year"}),
            "Month": Suggest("date", {"part": "month"}),
            "Day": Suggest("date", {"part": "day"}),
            "Created": "date",
        }
    )

    assert _ymd(text, mapping) == (2019, 3, 7)


def test_parse_csv_text__fills_missing_parts_from_date_column() -> None:
    text = "Year,Created\n2020,2020-05-14\n"
    mapping = mapping_of({"Year": Suggest("date", {"part": "year"}), "Created": "date"})

    assert _ymd(text, mapping) == (2020, 5, 14)


def test_parse_csv_text__falls_back_to_date_when_ymd_cells_blank() -> None:
    text = "Year,Created\n,2020-05-14\n"
    mapping = mapping_of({"Year": Suggest("date", {"part": "year"}), "Created": "date"})

    assert _ymd(text, mapping) == (2020, 5, 14)


def test_parse_csv_text__unparseable_date_column_keeps_ymd() -> None:
    text = "Year,Created\n2020,sometime in May\n"
    mapping = mapping_of({"Year": Suggest("date", {"part": "year"}), "Created": "date"})

    assert _ymd(text, mapping) == (2020, None, None)


def test_parse_csv_text__maps_publication_year_and_create_date_together() -> None:
    text = "Publication Year,Create Date\n2018,2020-05-14\n"
    mapping = mapping_of(
        {"Publication Year": Suggest("date", {"part": "year"}), "Create Date": "date"}
    )

    assert _ymd(text, mapping) == (2018, 5, 14)


def test_parse_csv_file__falls_back_to_cp1252_on_decode_error() -> None:
    mapping = mapping_of({"Title": "title", "Author": "notes"})

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


def test_read_csv_headers__skips_row_with_cell_over_limit(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text(f"Title,Abstract\nA,{'x' * 1_000_001}\nB,short\n")

    summary = read_csv_headers(csv_path)

    assert summary.samples == {"Title": "B", "Abstract": "short"}
    assert summary.total_rows == 1


def test_read_csv_headers__empty_file_returns_empty_dict(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("")

    assert read_csv_headers(csv_path).samples == {}


def test_read_csv_headers__decodes_cp1252_file() -> None:
    samples = read_csv_headers(CSV_FIXTURES_DIR / "cp1252_encoded.csv").samples

    assert samples == {"Title": "Café Study", "Author": "Müller"}


@pytest.mark.parametrize(
    ("header", "expected_row"),
    [
        ("Article Title", ScalarRow(target="title")),
        ("Source title", ScalarRow(target="journal")),
        ("Author full names", AuthorsRow(id_key="author_full_names")),
        ("Author Keywords", KeywordsRow(delimiter=";")),
        ("DOI", ScalarRow(target="doi")),
        ("Document Type", ScalarRow(target="publication_type")),
        ("Year", DateRow(part="year")),
        ("Date", DateRow(part="full")),
        ("Page start", PagesRow(part="start")),
        ("Page end", PagesRow(part="end")),
        ("Page range", PagesRow(part="range")),
        ("ISSN", IssnIsbnRow(kind="issn")),
        ("ISBN", IssnIsbnRow(kind="isbn")),
        ("PMID", ScalarRow(target="pmid")),
        ("PMCID", OtherIdRow(key="pmcid")),
        ("PMC ID", OtherIdRow(key="pmc_id")),
    ],
)
def test_suggest_mapping__matches_known_vendor_headers(
    header: str, expected_row: RowMapping
) -> None:
    suggestions = suggest_mapping([header])

    assert suggestions.rows == {header: expected_row}


@pytest.mark.parametrize(
    ("header", "expected_key"),
    [
        ("Scopus Author ID", "scopus_author_id"),
        ("Custom ID", "custom_id"),
        ("Zotero ID", "zotero_id"),
    ],
)
def test_suggest_mapping__unmatched_id_header_falls_back_to_other_ids(
    header: str, expected_key: str
) -> None:
    suggestions = suggest_mapping([header])

    assert suggestions.rows == {header: OtherIdRow(key=expected_key)}


@pytest.mark.parametrize("header", ["Valid", "Wide", "Identifier", "Provider"])
def test_suggest_mapping__non_id_words_containing_id_stay_unmapped(
    header: str,
) -> None:
    suggestions = suggest_mapping([header])

    assert targets_of(suggestions) == {}


def test_suggest_mapping__ignored_keys_stay_unmapped() -> None:
    mapping = suggest_mapping(
        ["Conference name", "Conference date"],
        ignored_keys=frozenset({"conference date"}),
    )

    assert targets_of(mapping) == {"Conference name": "conference_name"}


def test_suggest_mapping__leaves_unrecognized_header_out() -> None:
    suggestions = suggest_mapping(["Zzzqqqxx123"])

    assert targets_of(suggestions) == {}


def test_suggest_mapping__keeps_every_column_per_date_part() -> None:
    suggestions = suggest_mapping(["Year", "Publication Year", "Date"])

    assert suggestions.rows == {
        "Year": DateRow(part="year"),
        "Publication Year": DateRow(part="year"),
        "Date": DateRow(part="full"),
    }


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


def test_parse_csv_record__applies_mapping() -> None:
    mapping = mapping_of({"Title": "title", "Authors": "authors"})
    raw_fields = {"Title": "Some Paper", "Authors": "Smith, J; Doe, J"}

    row = parse_csv_record(raw_fields, mapping)

    assert row.record.title == "Some Paper"
    assert row.record.author_names == "Smith, J; Doe, J"
    assert row.raw_fields == raw_fields


def test_parse_csv_file__tab_delimiter_maps_fields() -> None:
    mapping = mapping_of(
        {
            "title": "title",
            "authors": "authors",
            "doi": "doi",
            "keywords": "keywords",
            "year": Suggest("date", {"part": "year"}),
        }
    )

    result = parse_csv_file(
        CSV_FIXTURES_DIR / "tab_delimited.tsv", mapping, delimiter="\t"
    )

    assert result.skipped == []
    assert len(result.rows) == 3
    record = result.rows[0].record
    assert record.title == "Deep learning for screening, a review"
    assert record.author_names == "Smith, Jane; Doe, John"
    assert record.doi == "10.1000/abc123"
    assert record.keywords == ["active learning", "screening"]
    assert record.publication_date is not None
    assert record.publication_date.year == 2021


def test_parse_csv_text__tab_delimiter_keeps_commas_in_cells() -> None:
    text = "Title\tAuthors\nA, B, and C\tSmith, J\nD, E\tDoe, J\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping, delimiter="\t")

    assert result.skipped == []
    assert [row.record.title for row in result.rows] == ["A, B, and C", "D, E"]


def test_parse_csv_text__tab_delimiter_reads_quoted_multiline_cell() -> None:
    text = 'Title\tAbstract\nSome Paper\t"First line.\nSecond line with a\ttab."\n'
    mapping = mapping_of({"Abstract": "abstract"})

    result = parse_csv_text(text, mapping, delimiter="\t")

    assert result.skipped == []
    assert result.rows[0].record.abstract == "First line.\nSecond line with a\ttab."


def test_parse_csv_text__tab_delimiter_skips_ragged_row() -> None:
    text = "Title\tDOI\nSome Paper\t10.1/x\nOnly title\n"
    mapping = mapping_of({"Title": "title"})

    result = parse_csv_text(text, mapping, delimiter="\t")

    assert len(result.rows) == 1
    assert len(result.skipped) == 1
    assert "fewer fields" in result.skipped[0].reason


def test_read_csv_headers__tab_delimiter_returns_headers_and_counts() -> None:
    summary = read_csv_headers(CSV_FIXTURES_DIR / "tab_delimited.tsv", delimiter="\t")

    assert list(summary.samples) == [
        "record_id",
        "title",
        "abstract",
        "authors",
        "doi",
        "keywords",
        "year",
    ]
    assert summary.samples["authors"] == "Smith, Jane; Doe, John"
    assert summary.total_rows == 3
    assert summary.filled["doi"] == 2


@pytest.mark.parametrize(
    "header", ["included", "label_included", "Label", "Decision", "Inclusion"]
)
def test_suggest_mapping__matches_label_headers(header: str) -> None:
    suggestions = suggest_mapping([header])

    assert targets_of(suggestions) == {header: "label"}


def test_parse_csv_text__reads_asreview_style_included_column() -> None:
    text = "title,included\nA,1\nB,0\nC,-1\nD,\n"
    mapping = suggest_mapping(["title", "included"])

    result = parse_csv_text(text, mapping)

    assert [row.record.labels[0].value for row in result.rows] == [
        "include",
        "exclude",
        "unlabeled",
        "unlabeled",
    ]


def _fail_on_bad_title(monkeypatch: pytest.MonkeyPatch) -> None:
    real = csv_.apply_mapping

    def apply(
        raw_fields: dict[str, str], mapping: FieldMapping, settings: ParseSettings
    ) -> Record:
        if "Bad" in raw_fields.values():
            raise ValueError("bad value")
        return real(raw_fields, mapping, settings)

    monkeypatch.setattr(csv_, "apply_mapping", apply)


def test_parse_csv_text__skips_record_that_fails_to_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fail_on_bad_title(monkeypatch)

    result = csv_.parse_csv_text(
        "Title\nGood\nBad\nAlso good\n", mapping_of({"Title": "title"})
    )

    assert [row.record.title for row in result.rows] == ["Good", "Also good"]
    assert [row.row_number for row in result.rows] == [2, 4]
    assert result.skipped == [SkippedRow(3, "bad value")]
