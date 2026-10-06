from pathlib import Path

from app.parsers.mapping import FieldMapping
from app.parsers.ris import parse_ris_file, parse_ris_text

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
