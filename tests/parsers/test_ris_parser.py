from pathlib import Path

from app.parsers.mapping import FieldMapping
from app.parsers.ris import (
    parse_ris_file,
    parse_ris_text,
    read_ris_tags,
    suggest_ris_mapping,
)

RIS_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "ris"

_MAPPING = FieldMapping(
    targets={
        "TI": "title",
        "AU": "authors",
        "KW": "keywords",
        "AB": "abstract",
        "N1": "notes",
        "T2": "journal",
    },
    list_delimiter="\n",
)


def test_parse_ris_text__maps_scalar_fields() -> None:
    text = "TY  - JOUR\nTI  - Some Paper\nT2  - Nature\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert result.skipped == []
    record = result.rows[0].record
    assert record.title == "Some Paper"
    assert record.journal == "Nature"


def test_parse_ris_text__keeps_raw_fields_including_unmapped_tags() -> None:
    text = "TY  - JOUR\nTI  - Some Paper\nVL  - 12\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert result.rows[0].raw_fields == {
        "TY": "JOUR",
        "TI": "Some Paper",
        "VL": "12",
    }


def test_parse_ris_text__repeated_author_tags_become_separate_authors() -> None:
    text = "TY  - JOUR\nAU  - Smith, John\nAU  - Doe, Jane\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Smith, John", "Doe, Jane"]


def test_parse_ris_text__repeated_keyword_tags_collect_all() -> None:
    text = "TY  - JOUR\nKW  - nlp\nKW  - machine learning\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert result.rows[0].record.keywords == ["nlp", "machine learning"]


def test_parse_ris_text__repeated_tag_is_joined_with_newline_in_raw_fields() -> None:
    text = "TY  - JOUR\nN1  - first note\nN1  - second note\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert result.rows[0].raw_fields["N1"] == "first note\nsecond note"
    assert result.rows[0].record.notes == "first note\nsecond note"


def test_parse_ris_text__continuation_line_extends_previous_value() -> None:
    text = "TY  - JOUR\nAB  - First line.\nSecond line.\nKW  - nlp\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert result.rows[0].record.abstract == "First line.\nSecond line."
    assert result.rows[0].record.keywords == ["nlp"]


def test_parse_ris_text__parses_several_records_with_blank_lines() -> None:
    text = "TY  - JOUR\nTI  - One\nER  - \n\n\nTY  - JOUR\nTI  - Two\nER  - \n\n"

    result = parse_ris_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["One", "Two"]
    assert result.skipped == []


def test_parse_ris_text__handles_crlf_line_endings() -> None:
    text = "TY  - JOUR\r\nTI  - Some Paper\r\nER  - \r\n"

    result = parse_ris_text(text, _MAPPING)

    assert result.rows[0].record.title == "Some Paper"


def test_parse_ris_text__tag_with_empty_value_is_kept_empty() -> None:
    text = "TY  - JOUR\nTI  - \nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert result.rows[0].record.title is None
    assert result.rows[0].raw_fields["TI"] == ""


def test_parse_ris_text__skips_record_without_ty_tag() -> None:
    text = "TY  - JOUR\nTI  - Good\nER  - \n\nTI  - No type\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["Good"]
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 5
    assert "no TY" in result.skipped[0].reason


def test_parse_ris_text__skips_record_missing_er_terminator() -> None:
    text = "TY  - JOUR\nTI  - Good\nER  - \n\nTY  - JOUR\nTI  - Truncated\n"

    result = parse_ris_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["Good"]
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 5
    assert "ER" in result.skipped[0].reason


def test_parse_ris_text__skips_text_outside_a_record() -> None:
    text = "Exported from somewhere\nTY  - JOUR\nTI  - Good\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert len(result.rows) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 1
    assert "outside a record" in result.skipped[0].reason


def test_parse_ris_text__ignores_repeated_er_lines() -> None:
    text = "TY  - JOUR\nTI  - Good\nER  - \nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert len(result.rows) == 1
    assert result.skipped == []


def test_parse_ris_text__empty_text_gives_no_rows() -> None:
    result = parse_ris_text("", _MAPPING)

    assert result.rows == []
    assert result.skipped == []


def test_parse_ris_file__reads_realistic_export() -> None:
    result = parse_ris_file(RIS_FIXTURES_DIR / "scopus_style.ris", _MAPPING)

    assert result.skipped == []
    first, second = (row.record for row in result.rows)
    assert first.title == "Deep learning for systematic review screening"
    assert first.journal == "Journal of Biomedical Informatics"
    assert first.abstract == (
        "We evaluate neural classifiers for citation screening.\n"
        "Results show a large reduction in manual workload."
    )
    assert first.keywords == ["machine learning", "systematic review"]
    assert second.notes == "Preprint available\nPresented as a poster"


def test_parse_ris_file__falls_back_to_cp1252_on_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "export.ris"
    path.write_bytes("TY  - JOUR\nTI  - Café Study\nER  - \n".encode("cp1252"))

    result = parse_ris_file(path, _MAPPING)

    assert result.rows[0].record.title == "Café Study"


def test_parse_ris_file__strips_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "export.ris"
    path.write_bytes("﻿TY  - JOUR\nTI  - Some Paper\nER  - \n".encode())

    result = parse_ris_file(path, _MAPPING)

    assert result.skipped == []
    assert result.rows[0].record.title == "Some Paper"


def test_suggest_ris_mapping__maps_common_tags() -> None:
    tags = ["TY", "TI", "AU", "T2", "VL", "IS", "SP", "EP", "DO", "KW", "AB", "UR"]

    suggestions = suggest_ris_mapping(tags)

    assert suggestions.targets == {
        "TY": "publication_type",
        "TI": "title",
        "AU": "authors",
        "T2": "journal",
        "VL": "volume",
        "IS": "issue",
        "SP": "page_start",
        "EP": "page_end",
        "DO": "doi",
        "KW": "keywords",
        "AB": "abstract",
        "UR": "url",
    }


def test_suggest_ris_mapping__uses_newline_list_delimiter() -> None:
    assert suggest_ris_mapping(["AU"]).list_delimiter == "\n"


def test_suggest_ris_mapping__prefers_da_over_py_for_date() -> None:
    suggestions = suggest_ris_mapping(["PY", "DA", "Y1"])

    assert suggestions.targets == {"DA": "date"}


def test_suggest_ris_mapping__falls_back_to_py_without_da() -> None:
    suggestions = suggest_ris_mapping(["PY"])

    assert suggestions.targets == {"PY": "date"}


def test_suggest_ris_mapping__first_of_alternate_title_tags_wins_in_parse() -> None:
    suggestions = suggest_ris_mapping(["T1", "TI"])
    text = "TY  - JOUR\nT1  - Primary\nTI  - Other\nER  - \n"

    result = parse_ris_text(text, suggestions)

    assert result.rows[0].record.title == "Primary"


def test_suggest_ris_mapping__routes_accession_number_to_other_ids() -> None:
    suggestions = suggest_ris_mapping(["AN"])

    assert suggestions.targets == {"AN": "other_ids.an"}


def test_suggest_ris_mapping__maps_sn_to_issn_isbn() -> None:
    assert suggest_ris_mapping(["SN"]).targets == {"SN": "issn_isbn"}


def test_suggest_ris_mapping__leaves_unknown_tags_unmapped() -> None:
    assert suggest_ris_mapping(["ZZ", "TZ"]).targets == {}


def test_parse_ris_text__sn_routes_to_issn_or_isbn_by_value() -> None:
    mapping = suggest_ris_mapping(["SN"])
    text = (
        "TY  - JOUR\nSN  - 1234-5678\nER  - \n"
        "TY  - BOOK\nSN  - 978-3-16-148410-0\nER  - \n"
    )

    journal, book = (row.record for row in parse_ris_text(text, mapping).rows)

    assert (journal.issn, journal.isbn) == ("1234-5678", None)
    assert (book.issn, book.isbn) == (None, "978-3-16-148410-0")


def test_parse_ris_file__default_mapping_on_realistic_export() -> None:
    path = RIS_FIXTURES_DIR / "scopus_style.ris"
    tags = ["TY", "AU", "TI", "T2", "PY", "DA", "VL", "IS", "SP", "EP", "DO"]

    result = parse_ris_file(path, suggest_ris_mapping(tags))

    first = result.rows[0].record
    assert first.publication_type == "JOUR"
    assert [author.full_name for author in first.authors] == [
        "Smith, John A.",
        "Doe, Jane",
    ]
    assert first.pages == "100-110"
    assert first.doi == "10.1016/j.jbi.2020.1"
    assert first.publication_date is not None
    assert (
        first.publication_date.year,
        first.publication_date.month,
        first.publication_date.day,
    ) == (2020, 5, 14)


def test_read_ris_tags__returns_distinct_tags_in_first_seen_order_without_er() -> None:
    samples = read_ris_tags(RIS_FIXTURES_DIR / "scopus_style.ris").samples

    assert list(samples) == [
        "TY", "AU", "TI", "T2", "PY", "DA", "VL", "IS", "SP", "EP",
        "DO", "AB", "KW", "SN", "UR", "N1",
    ]  # fmt: skip


def test_read_ris_tags__sample_is_first_occurrence_of_tag() -> None:
    samples = read_ris_tags(RIS_FIXTURES_DIR / "scopus_style.ris").samples

    assert samples["TY"] == "JOUR"
    assert samples["AU"] == "Smith, John A."
    assert samples["TI"] == "Deep learning for systematic review screening"


def test_read_ris_tags__sample_skips_empty_occurrence_to_first_non_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "export.ris"
    path.write_text("TY  - JOUR\nN1  -\nER  -\n\nTY  - JOUR\nN1  - a note\nER  -\n")

    assert read_ris_tags(path).samples == {"TY": "JOUR", "N1": "a note"}


def test_read_ris_tags__empty_file_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "empty.ris"
    path.write_text("")

    assert read_ris_tags(path).samples == {}


def test_read_ris_tags__counts_records_and_records_with_a_value_per_tag(
    tmp_path: Path,
) -> None:
    path = tmp_path / "export.ris"
    path.write_text(
        "TY  - JOUR\nAU  - A\nAU  - B\nN1  -\nER  -\n\n"
        "TY  - JOUR\nN1  - a note\nER  -\n"
    )

    summary = read_ris_tags(path)

    assert summary.total_rows == 2
    assert summary.filled == {"TY": 2, "AU": 1, "N1": 1}


def test_read_ris_tags__record_without_er_terminator_still_counts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "export.ris"
    path.write_text("TY  - JOUR\nER  -\n\nTY  - JOUR\nTI  - Unfinished\n")

    assert read_ris_tags(path).total_rows == 2


def test_read_ris_tags__empty_file_has_zero_rows(tmp_path: Path) -> None:
    path = tmp_path / "empty.ris"
    path.write_text("")

    assert read_ris_tags(path).total_rows == 0
