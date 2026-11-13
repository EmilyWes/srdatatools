from pathlib import Path

import pytest

import app.parsers.mapping as mapping_module
from app.models.record import Record
from app.parsers import ris
from app.parsers.common import SkippedRow
from app.parsers.mapping import (
    AuthorsRow,
    FieldMapping,
    KeywordsRow,
    OtherIdRow,
    PagesRow,
    Suggest,
)
from app.parsers.profiles.default import DEFAULT_PROFILES
from app.parsers.quirks import ParseSettings
from app.parsers.ris import (
    parse_ris_file,
    parse_ris_record,
    parse_ris_text,
    read_ris_tags,
    suggest_ris_mapping,
)
from tests.mappings import mapping_of, targets_of

_AFFILIATIONS = Suggest("authors", {"role": "affiliations"})
_IDS = Suggest("authors", {"role": "ids"})

RIS_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "general"

_MAPPING = mapping_of(
    {
        "TI": "title",
        "AU": "authors",
        "KW": "keywords",
        "AB": "abstract",
        "N1": "notes",
        "T2": "journal",
    },
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

    assert result.rows[0].record.author_names == "Smith, John|Doe, Jane"


_AFFILIATION_MAPPING = mapping_of(
    {"TI": "title", "AU": "authors", "AD": _AFFILIATIONS, "C1": _AFFILIATIONS},
)


def test_parse_ris_text__joins_affiliation_lines_in_order() -> None:
    text = (
        "TY  - JOUR\nAU  - Smith, John\nAD  - Uni A\nAD  - Uni B\n"
        "AU  - Doe, Jane\nAD  - Uni C\nER  - \n"
    )

    record = parse_ris_text(text, _AFFILIATION_MAPPING).rows[0].record

    assert record.author_names == "Smith, John|Doe, Jane"
    assert record.author_affiliations == "Uni A|Uni B|Uni C"


def test_parse_ris_text__first_affiliation_tag_with_lines_wins() -> None:
    text = "TY  - JOUR\nAU  - Smith, John\nC1  - Uni A\nAD  - Uni B\nER  - \n"

    record = parse_ris_text(text, _AFFILIATION_MAPPING).rows[0].record

    assert record.author_affiliations == "Uni B"


def test_parse_ris_text__keeps_affiliations_listed_after_all_authors() -> None:
    text = (
        "TY  - JOUR\nAU  - Smith, John\nAU  - Doe, Jane\nTI  - Some Paper\n"
        "AD  - Uni A\nAD  - Uni B\nER  - \n"
    )

    record = parse_ris_text(text, _AFFILIATION_MAPPING).rows[0].record

    assert record.author_affiliations == "Uni A|Uni B"


_ID_MAPPING = mapping_of(
    {
        "TI": "title",
        "AU": "authors",
        "AD": _AFFILIATIONS,
        "ID": Suggest("authors", {"role": "ids", "id_key": "orcid"}),
    },
)


def test_parse_ris_text__id_line_belongs_to_the_author_above() -> None:
    text = (
        "TY  - JOUR\nAU  - Smith, John\nAD  - Uni A\n"
        "ID  - https://orcid.org/0000-0001-2345-6789\n"
        "AU  - Doe, Jane\nAU  - Roe, Rick\nID  - 0000-0002-0000-0000\nER  - \n"
    )

    record = parse_ris_text(text, _ID_MAPPING).rows[0].record

    assert record.author_ids == ("orcid:0000-0001-2345-6789||orcid:0000-0002-0000-0000")


def test_parse_ris_text__other_tag_ends_the_author_for_id_lines() -> None:
    text = (
        "TY  - JOUR\nAU  - Smith, John\nTI  - Some Paper\n"
        "ID  - 0000-0001-2345-6789\nER  - \n"
    )

    record = parse_ris_text(text, _ID_MAPPING).rows[0].record

    assert record.author_ids is None


def test_parse_ris_text__unmapped_affiliation_tag_is_ignored() -> None:
    text = "TY  - JOUR\nAU  - Smith, John\nC1  - Uni A\nER  - \n"

    record = parse_ris_text(text, _MAPPING).rows[0].record

    assert record.author_names == "Smith, John"
    assert record.author_affiliations is None


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


def test_parse_ris_text__ignores_text_outside_a_record() -> None:
    text = "Exported from somewhere\nTY  - JOUR\nTI  - Good\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["Good"]
    assert result.skipped == []


def test_parse_ris_text__ignores_asreview_record_numbers() -> None:
    text = "1.\nTY  - JOUR\nTI  - A\nER  - \n\n2.\nTY  - JOUR\nTI  - B\nER  - \n"

    result = parse_ris_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["A", "B"]
    assert result.skipped == []


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

    assert targets_of(suggestions) == {
        "TY": "publication_type",
        "TI": "title",
        "AU": "authors",
        "T2": "journal",
        "VL": "volume",
        "IS": "issue",
        "SP": "pages",
        "EP": "pages",
        "DO": "doi",
        "KW": "keywords",
        "AB": "abstract",
        "UR": "url",
    }


def test_suggest_ris_mapping__uses_row_options() -> None:
    suggestions = suggest_ris_mapping(["AU", "AD", "KW", "SP", "EP"])

    assert suggestions.rows == {
        "AU": AuthorsRow(id_key="au"),
        "AD": AuthorsRow(role="affiliations", id_key="ad"),
        "KW": KeywordsRow(),
        "SP": PagesRow(part="start"),
        "EP": PagesRow(part="end"),
    }


def test_suggest_ris_mapping__maps_every_date_tag() -> None:
    suggestions = suggest_ris_mapping(["PY", "DA", "Y1"])

    assert targets_of(suggestions) == {"PY": "date", "DA": "date", "Y1": "date"}


def test_parse_ris_text__default_settings_read_da_before_py() -> None:
    text = "TY  - JOUR\nPY  - 2020\nDA  - 2020/03/15/\nER  - \n"
    mapping = suggest_ris_mapping(["PY", "DA"])

    result = parse_ris_text(text, mapping, DEFAULT_PROFILES["ris"].settings)

    assert result.rows[0].record.publication_date == "2020/03/15/"


def test_parse_ris_text__keeps_names_as_in_the_file() -> None:
    text = "TY  - JOUR\nAU  - Smith, John\nAU  - Madonna\nER  - \n"

    result = parse_ris_text(text, suggest_ris_mapping(["AU"]))

    assert result.rows[0].record.author_names == "Smith, John|Madonna"


def test_suggest_ris_mapping__first_of_alternate_title_tags_wins_in_parse() -> None:
    suggestions = suggest_ris_mapping(["T1", "TI"])
    text = "TY  - JOUR\nT1  - Primary\nTI  - Other\nER  - \n"

    result = parse_ris_text(text, suggestions)

    assert result.rows[0].record.title == "Primary"


def test_suggest_ris_mapping__routes_accession_number_to_other_ids() -> None:
    suggestions = suggest_ris_mapping(["AN"])

    assert suggestions.rows == {"AN": OtherIdRow(key="an")}


def test_suggest_ris_mapping__maps_ad_to_authors() -> None:
    assert targets_of(suggest_ris_mapping(["AU", "AD"])) == {
        "AU": "authors",
        "AD": "authors",
    }


def test_suggest_ris_mapping__maps_sn_to_issn_isbn() -> None:
    assert targets_of(suggest_ris_mapping(["SN"])) == {"SN": "issn_isbn"}


def test_suggest_ris_mapping__applies_alias_overrides() -> None:
    mapping = suggest_ris_mapping(
        ["TY", "M3"],
        overrides={"m3": Suggest("publication_type")},
        ignored_keys=frozenset({"ty"}),
    )

    assert targets_of(mapping) == {"M3": "publication_type"}


def test_suggest_ris_mapping__leaves_unknown_tags_unmapped() -> None:
    assert targets_of(suggest_ris_mapping(["ZZ", "TZ"])) == {}


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
    assert first.author_names == "Smith, John A.|Doe, Jane"
    assert first.pages == "100-110"
    assert first.doi == "10.1016/j.jbi.2020.1"
    assert first.publication_date == "2020///"


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


def test_parse_ris_record__joins_repeated_tags() -> None:
    lines = [("AU", "Smith, John"), ("AU", "Doe, Jane"), ("TI", "Some Paper")]

    row = parse_ris_record(lines, _MAPPING)

    assert row.record.author_names == "Smith, John|Doe, Jane"
    assert row.record.title == "Some Paper"
    assert row.raw_fields["AU"] == "Smith, John\nDoe, Jane"


def _fail_on_bad_title(monkeypatch: pytest.MonkeyPatch) -> None:
    real = mapping_module.apply_mapping

    def apply(
        raw_fields: dict[str, str], mapping: FieldMapping, settings: ParseSettings
    ) -> Record:
        if "Bad" in raw_fields.values():
            raise ValueError("bad value")
        return real(raw_fields, mapping, settings)

    monkeypatch.setattr(mapping_module, "apply_mapping", apply)


def test_parse_ris_text__skips_record_that_fails_to_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fail_on_bad_title(monkeypatch)
    text = (
        "TY  - JOUR\nTI  - Good\nER  - \n"
        "TY  - JOUR\nTI  - Bad\nER  - \n"
        "TY  - JOUR\nTI  - Also good\nER  - \n"
    )

    result = ris.parse_ris_text(text, mapping_of({"TI": "title"}))

    assert [row.record.title for row in result.rows] == ["Good", "Also good"]
    assert [row.row_number for row in result.rows] == [1, 7]
    assert result.skipped == [SkippedRow(4, "bad value")]
