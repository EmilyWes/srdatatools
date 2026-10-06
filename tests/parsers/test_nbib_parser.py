from pathlib import Path

from app.parsers.mapping import FieldMapping
from app.parsers.nbib import (
    parse_nbib_file,
    parse_nbib_text,
    read_nbib_tags,
    suggest_nbib_mapping,
)

NBIB_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "nbib"

_MAPPING = FieldMapping(
    targets={
        "TI": "title",
        "FAU": "authors",
        "OT": "keywords",
        "AB": "abstract",
        "JT": "journal",
        "DOI": "doi",
    },
    list_delimiter="\n",
)


def test_parse_nbib_text__maps_scalar_fields() -> None:
    text = "PMID- 1\nTI  - Some Paper\nJT  - Nature\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.skipped == []
    record = result.rows[0].record
    assert record.title == "Some Paper"
    assert record.journal == "Nature"


def test_parse_nbib_text__keeps_raw_fields_including_unmapped_tags() -> None:
    text = "PMID- 1\nTI  - Some Paper\nVI  - 12\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].raw_fields == {
        "PMID": "1",
        "TI": "Some Paper",
        "VI": "12",
    }


def test_parse_nbib_text__repeated_author_tags_become_separate_authors() -> None:
    text = "PMID- 1\nFAU - Smith, John\nFAU - Doe, Jane\n"

    result = parse_nbib_text(text, _MAPPING)

    authors = result.rows[0].record.authors
    assert [author.full_name for author in authors] == ["Smith, John", "Doe, Jane"]


def test_parse_nbib_text__repeated_keyword_tags_collect_all() -> None:
    text = "PMID- 1\nOT  - nlp\nOT  - machine learning\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.keywords == ["nlp", "machine learning"]
    assert result.rows[0].raw_fields["OT"] == "nlp\nmachine learning"


def test_parse_nbib_text__continuation_line_is_joined_with_a_space() -> None:
    text = "PMID- 1\nAB  - First line\n      second line.\nOT  - nlp\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.abstract == "First line second line."
    assert result.rows[0].record.keywords == ["nlp"]


def test_parse_nbib_text__parses_several_records_split_on_blank_lines() -> None:
    text = "PMID- 1\nTI  - One\n\n\nPMID- 2\nTI  - Two\n\n"

    result = parse_nbib_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["One", "Two"]
    assert result.skipped == []


def test_parse_nbib_text__handles_crlf_line_endings() -> None:
    text = "PMID- 1\r\nTI  - Some Paper\r\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.title == "Some Paper"


def test_parse_nbib_text__tag_with_empty_value_is_kept_empty() -> None:
    text = "PMID- 1\nTI  - \n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.title is None
    assert result.rows[0].raw_fields["TI"] == ""


def test_parse_nbib_text__doi_is_taken_from_aid_without_suffix() -> None:
    text = "PMID- 1\nAID - S1-2 [pii]\nAID - 10.1/abc [doi]\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.doi == "10.1/abc"
    assert result.rows[0].raw_fields["AID"] == "S1-2 [pii]\n10.1/abc [doi]"


def test_parse_nbib_text__doi_falls_back_to_lid() -> None:
    text = "PMID- 1\nLID - 10.1/abc [doi]\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.doi == "10.1/abc"


def test_parse_nbib_text__doi_prefers_aid_over_lid() -> None:
    text = "PMID- 1\nLID - 10.1/lid [doi]\nAID - 10.1/aid [doi]\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].raw_fields["DOI"] == "10.1/aid"


def test_parse_nbib_text__no_doi_id_leaves_doi_unset() -> None:
    text = "PMID- 1\nAID - S1-2 [pii]\n"

    result = parse_nbib_text(text, _MAPPING)

    assert result.rows[0].record.doi is None
    assert "DOI" not in result.rows[0].raw_fields


def test_parse_nbib_text__skips_record_without_pmid() -> None:
    text = "PMID- 1\nTI  - Good\n\nTI  - No id\nJT  - X\n"

    result = parse_nbib_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["Good"]
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 4
    assert "no PMID" in result.skipped[0].reason


def test_parse_nbib_text__skips_text_outside_a_record() -> None:
    text = "Exported from somewhere\n\nPMID- 1\nTI  - Good\n"

    result = parse_nbib_text(text, _MAPPING)

    assert len(result.rows) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].row_number == 1
    assert "outside a record" in result.skipped[0].reason


def test_parse_nbib_text__empty_text_gives_no_rows() -> None:
    result = parse_nbib_text("", _MAPPING)

    assert result.rows == []
    assert result.skipped == []


def test_parse_nbib_file__reads_realistic_export() -> None:
    result = parse_nbib_file(NBIB_FIXTURES_DIR / "pubmed_style.nbib", _MAPPING)

    assert result.skipped == []
    first, second = (row.record for row in result.rows)
    assert first.title == (
        "Deep learning for systematic review screening: a title long enough "
        "to wrap onto a second line."
    )
    assert first.journal == "Journal of Biomedical Informatics"
    assert first.abstract == (
        "We evaluate neural classifiers for citation screening. "
        "Results show a large reduction in manual workload."
    )
    assert first.doi == "10.1016/j.jbi.2020.1"
    assert first.keywords == ["machine learning", "systematic review"]
    assert second.doi is None


def test_parse_nbib_file__falls_back_to_cp1252_on_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "export.nbib"
    path.write_bytes("PMID- 1\nTI  - Café Study\n".encode("cp1252"))

    result = parse_nbib_file(path, _MAPPING)

    assert result.rows[0].record.title == "Café Study"


def test_parse_nbib_file__strips_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "export.nbib"
    path.write_bytes("﻿PMID- 1\nTI  - Some Paper\n".encode())

    result = parse_nbib_file(path, _MAPPING)

    assert result.skipped == []
    assert result.rows[0].record.title == "Some Paper"


def test_suggest_nbib_mapping__maps_common_tags() -> None:
    tags = ["PMID", "TI", "FAU", "JT", "VI", "IP", "PG", "DOI", "AB", "LA", "PT"]

    suggestions = suggest_nbib_mapping(tags)

    assert suggestions.targets == {
        "PMID": "pmid",
        "TI": "title",
        "FAU": "authors",
        "JT": "journal",
        "VI": "volume",
        "IP": "issue",
        "PG": "pages",
        "DOI": "doi",
        "AB": "abstract",
        "LA": "language",
        "PT": "publication_type",
    }


def test_suggest_nbib_mapping__uses_newline_list_delimiter() -> None:
    assert suggest_nbib_mapping(["FAU"]).list_delimiter == "\n"


def test_suggest_nbib_mapping__leaves_abbreviated_authors_unmapped() -> None:
    assert suggest_nbib_mapping(["FAU", "AU"]).targets == {"FAU": "authors"}


def test_suggest_nbib_mapping__maps_dp_to_date_and_keywords_from_ot_and_mh() -> None:
    suggestions = suggest_nbib_mapping(["DP", "OT", "MH"])

    assert suggestions.targets == {"DP": "date", "OT": "keywords", "MH": "keywords"}


def test_suggest_nbib_mapping__routes_pmc_and_mid_to_other_ids() -> None:
    suggestions = suggest_nbib_mapping(["PMC", "MID"])

    assert suggestions.targets == {"PMC": "other_ids.pmc", "MID": "other_ids.mid"}


def test_suggest_nbib_mapping__leaves_unknown_tags_unmapped() -> None:
    assert suggest_nbib_mapping(["OWN", "STAT", "ZZ"]).targets == {}


def test_parse_nbib_file__default_mapping_on_realistic_export() -> None:
    path = NBIB_FIXTURES_DIR / "pubmed_style.nbib"

    result = parse_nbib_file(path, suggest_nbib_mapping(read_nbib_tags(path)))

    first, second = (row.record for row in result.rows)
    assert first.pmid == "31234567"
    assert [author.full_name for author in first.authors] == [
        "Smith, John A",
        "Doe, Jane",
    ]
    assert first.pages == "100-110"
    assert first.doi == "10.1016/j.jbi.2020.1"
    assert first.other_ids == {"pmc": "PMC7000001"}
    assert first.publication_date is not None
    assert (
        first.publication_date.year,
        first.publication_date.month,
        first.publication_date.day,
    ) == (2020, 5, 14)
    assert second.keywords == ["Humans", "Review Literature as Topic"]
    assert second.publication_date is not None
    assert (second.publication_date.year, second.publication_date.month) == (2019, 1)


def test_read_nbib_tags__returns_distinct_tags_in_first_seen_order_with_doi() -> None:
    tags = read_nbib_tags(NBIB_FIXTURES_DIR / "pubmed_style.nbib")

    assert tags == [
        "PMID", "OWN", "STAT", "DP", "TI", "PG", "LID", "DOI", "AB", "FAU", "AU",
        "LA", "PT", "JT", "TA", "VI", "IP", "AID", "OT", "PMC", "IS", "MH",
    ]  # fmt: skip


def test_read_nbib_tags__empty_file_returns_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "empty.nbib"
    path.write_text("")

    assert read_nbib_tags(path) == []
