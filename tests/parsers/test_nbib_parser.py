from pathlib import Path

import pytest

import app.parsers.mapping as mapping_module
from app.models.record import Record
from app.parsers import nbib
from app.parsers.common import SkippedRow
from app.parsers.mapping import (
    AuthorsRow,
    FieldMapping,
    IssnIsbnRow,
    KeywordsRow,
    OtherIdRow,
    Suggest,
)
from app.parsers.nbib import (
    ROW_DEFAULTS,
    parse_nbib_file,
    parse_nbib_record,
    parse_nbib_text,
    read_nbib_tags,
    suggest_nbib_mapping,
)
from app.parsers.profiles.default import DEFAULT_PROFILES
from app.parsers.quirks import ParseSettings
from tests.mappings import mapping_of, targets_of

_NBIB_SETTINGS = DEFAULT_PROFILES["nbib"].settings

_AFFILIATIONS = Suggest("authors", {"role": "affiliations"})
_IDS = Suggest("authors", {"role": "ids"})

NBIB_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "general"

_MAPPING = mapping_of(
    {
        "TI": "title",
        "FAU": "authors",
        "OT": "keywords",
        "AB": "abstract",
        "JT": "journal",
        "DOI": "doi",
    },
    defaults=ROW_DEFAULTS,
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

    assert result.rows[0].record.author_names == "Smith, John|Doe, Jane"


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

    assert targets_of(suggestions) == {
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


def test_suggest_nbib_mapping__uses_row_options() -> None:
    suggestions = suggest_nbib_mapping(["FAU", "AUID", "AD", "MH"])

    assert suggestions.rows == {
        "FAU": AuthorsRow(id_key="fau"),
        "AUID": AuthorsRow(role="ids", id_key="auid"),
        "AD": AuthorsRow(role="affiliations", id_key="ad"),
        "MH": KeywordsRow(prefix="MeSH"),
    }


def test_suggest_nbib_mapping__alias_overrides_replace_defaults() -> None:
    suggestions = suggest_nbib_mapping(["TA", "JT"], {"jt": Suggest("journal")})

    assert targets_of(suggestions) == {"JT": "journal"}


def test_suggest_nbib_mapping__prefers_fau_over_au_for_authors() -> None:
    assert targets_of(suggest_nbib_mapping(["AU", "FAU"])) == {"FAU": "authors"}


def test_suggest_nbib_mapping__falls_back_to_au_without_fau() -> None:
    assert targets_of(suggest_nbib_mapping(["AU"])) == {"AU": "authors"}


def test_suggest_nbib_mapping__maps_dp_to_date_and_keywords_from_ot_and_mh() -> None:
    suggestions = suggest_nbib_mapping(["DP", "OT", "MH"])

    assert targets_of(suggestions) == {"DP": "date", "OT": "keywords", "MH": "keywords"}


def test_suggest_nbib_mapping__routes_pmc_and_mid_to_other_ids() -> None:
    suggestions = suggest_nbib_mapping(["PMC", "MID"])

    assert suggestions.rows == {
        "PMC": OtherIdRow(key="pmc"),
        "MID": OtherIdRow(key="mid"),
    }


def test_suggest_nbib_mapping__maps_is_to_issn_and_isbn_tag_to_isbn() -> None:
    suggestions = suggest_nbib_mapping(["IS", "ISBN"])

    assert suggestions.rows == {
        "IS": IssnIsbnRow(kind="issn"),
        "ISBN": IssnIsbnRow(kind="isbn"),
    }


def test_parse_nbib_text__isbn_tag_fills_isbn() -> None:
    text = "PMID- 1\nIS  - 1234-5678 (Print)\nISBN- 978-3-16-148410-0\n"

    mapping = suggest_nbib_mapping(["IS", "ISBN"])

    record = parse_nbib_text(text, mapping, _NBIB_SETTINGS).rows[0].record

    assert record.issn == "1234-5678 (Print)"
    assert record.isbn == "978-3-16-148410-0"


def _parse_issn(text: str) -> str | None:
    result = parse_nbib_text(text, suggest_nbib_mapping(["IS"]), _NBIB_SETTINGS)
    return result.rows[0].record.issn


def test_parse_nbib_text__is_raw_fields_keep_qualifiers() -> None:
    text = "PMID- 1\nIS  - 1234-5678 (Print)\nIS  - 8765-4321 (Electronic)\n"

    row = parse_nbib_text(text, suggest_nbib_mapping(["IS"])).rows[0]

    assert row.raw_fields["IS"] == "1234-5678 (Print)\n8765-4321 (Electronic)"


def test_parse_nbib_text__is_without_qualifier_unchanged() -> None:
    assert _parse_issn("PMID- 1\nIS  - 1234-5678\n") == "1234-5678"


def test_suggest_nbib_mapping__leaves_unknown_tags_unmapped() -> None:
    assert targets_of(suggest_nbib_mapping(["OWN", "STAT", "ZZ"])) == {}


def test_parse_nbib_file__default_mapping_on_realistic_export() -> None:
    path = NBIB_FIXTURES_DIR / "pubmed_style.nbib"

    result = parse_nbib_file(
        path, suggest_nbib_mapping(list(read_nbib_tags(path).samples)), _NBIB_SETTINGS
    )

    first, second = (row.record for row in result.rows)
    assert first.pmid == "31234567"
    assert first.author_names == "Smith, John A|Doe, Jane"
    assert first.pages == "100-110"
    assert first.doi == "10.1016/j.jbi.2020.1"
    assert first.other_ids == {"pmc": "PMC7000001"}
    assert first.issn == "1532-0480 (Electronic)"
    assert first.publication_date == "2020 May 14"
    assert second.keywords == ["[MeSH] Humans", "[MeSH] Review Literature as Topic"]
    assert second.publication_date == "2019 Jan-Feb"


def test_read_nbib_tags__returns_distinct_tags_in_first_seen_order_with_doi() -> None:
    samples = read_nbib_tags(NBIB_FIXTURES_DIR / "pubmed_style.nbib").samples

    assert list(samples) == [
        "PMID", "OWN", "STAT", "DP", "TI", "PG", "LID", "DOI", "AB", "FAU", "AU",
        "LA", "PT", "JT", "TA", "VI", "IP", "AID", "OT", "PMC", "IS", "MH",
    ]  # fmt: skip


def test_read_nbib_tags__sample_is_first_occurrence_of_tag() -> None:
    samples = read_nbib_tags(NBIB_FIXTURES_DIR / "pubmed_style.nbib").samples

    assert samples["PMID"] == "31234567"
    assert samples["FAU"] == "Smith, John A"
    assert samples["OT"] == "machine learning"
    assert samples["AID"] == "S1532-0464(20)30001-1 [pii]"


def test_read_nbib_tags__doi_sample_is_doi_without_suffix() -> None:
    samples = read_nbib_tags(NBIB_FIXTURES_DIR / "pubmed_style.nbib").samples

    assert samples["DOI"] == "10.1016/j.jbi.2020.1"


def test_read_nbib_tags__empty_file_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "empty.nbib"
    path.write_text("")

    assert read_nbib_tags(path).samples == {}


def test_read_nbib_tags__counts_records_and_records_with_a_value_per_tag(
    tmp_path: Path,
) -> None:
    path = tmp_path / "export.nbib"
    path.write_text("PMID- 1\nTI  - A\nAB  -\n\nPMID- 2\nTI  - B\nTI  - C\n")

    summary = read_nbib_tags(path)

    assert summary.total_rows == 2
    assert summary.filled == {"PMID": 2, "TI": 2, "AB": 0}


def test_read_nbib_tags__doi_from_id_tag_counts_as_filled_doi(tmp_path: Path) -> None:
    path = tmp_path / "export.nbib"
    path.write_text("PMID- 1\nLID - 10.1/xyz [doi]\n\nPMID- 2\nAID - S1532 [pii]\n")

    summary = read_nbib_tags(path)

    assert summary.filled["DOI"] == 1
    assert summary.filled["AID"] == 1


def test_read_nbib_tags__empty_file_has_zero_rows(tmp_path: Path) -> None:
    path = tmp_path / "empty.nbib"
    path.write_text("")

    assert read_nbib_tags(path).total_rows == 0


_AUTHOR_MAPPING = mapping_of(
    {"FAU": "authors", "AUID": _IDS, "AD": _AFFILIATIONS},
    defaults=ROW_DEFAULTS,
)


def _parse_authors(text: str, mapping: FieldMapping = _AUTHOR_MAPPING) -> Record:
    return parse_nbib_text(text, mapping).rows[0].record


def test_parse_nbib_text__auid_orcid_attaches_to_preceding_author() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "FAU - Doe, Jane\n"
        "AUID- ORCID: 0000-0002-6000-6450\n"
    )

    record = _parse_authors(text)

    assert record.author_ids == "orcid:0000-0001-8894-9875|orcid:0000-0002-6000-6450"


def test_parse_nbib_text__orcid_url_prefix_is_stripped() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: https://orcid.org/0000-0001-8894-9875\n"
        "FAU - Doe, Jane\n"
        "AUID- ORCID: http://orcid.org/0000-0002-6000-6450\n"
    )

    record = _parse_authors(text)

    assert record.author_ids == "orcid:0000-0001-8894-9875|orcid:0000-0002-6000-6450"


def test_parse_nbib_text__non_orcid_auid_keeps_its_scheme_as_key() -> None:
    text = "PMID- 1\nFAU - Smith, John\nAUID- ISNI: 0000 0001 2345 6789\n"

    assert _parse_authors(text).author_ids == "isni:0000 0001 2345 6789"


def test_parse_nbib_text__auid_without_scheme_uses_row_id_key() -> None:
    text = "PMID- 1\nFAU - Smith, John\nAUID- 12345\n"

    assert _parse_authors(text).author_ids == "auid:12345"


def test_parse_nbib_text__several_auids_of_one_author_share_a_slot() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AUID- ISNI: 1\n"
    )

    assert _parse_authors(text).author_ids == "orcid:0000-0001-8894-9875, isni:1"


def test_parse_nbib_text__ad_lines_are_joined_in_order() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AD  - Department A, University X.\n"
        "AD  - Department B, University Y. smith@example.org.\n"
        "FAU - Doe, Jane\n"
        "AD  - Department C, University Z.\n"
    )

    assert _parse_authors(text).author_affiliations == (
        "Department A, University X."
        "|Department B, University Y. smith@example.org."
        "|Department C, University Z."
    )


def test_parse_nbib_text__ad_continuation_line_is_joined() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AD  - Department of Geosciences, Virginia Tech,\n"
        "      Blacksburg, VA, USA.\n"
    )

    assert _parse_authors(text).author_affiliations == (
        "Department of Geosciences, Virginia Tech, Blacksburg, VA, USA."
    )


def test_parse_nbib_text__author_without_auid_keeps_an_empty_id_slot() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "FAU - Doe, Jane\n"
        "AUID- ORCID: 0000-0002-6000-6450\n"
    )

    assert _parse_authors(text).author_ids == "|orcid:0000-0002-6000-6450"


def test_parse_nbib_text__auid_ad_before_first_author_are_ignored() -> None:
    text = (
        "PMID- 1\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AD  - Department A.\n"
        "FAU - Smith, John\n"
    )

    record = _parse_authors(text)

    assert (record.author_ids, record.author_affiliations) == (None, None)


def test_parse_nbib_text__au_fallback_author_tag_groups_auid() -> None:
    mapping = mapping_of(
        {"AU": "authors", "AUID": _IDS, "AD": _AFFILIATIONS},
        defaults=ROW_DEFAULTS,
    )
    text = (
        "PMID- 1\n"
        "AU  - Smith J\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AU  - Doe J\n"
        "AD  - Department A.\n"
    )

    record = _parse_authors(text, mapping)

    assert record.author_names == "Smith J|Doe J"
    assert record.author_ids == "orcid:0000-0001-8894-9875|"
    assert record.author_affiliations == "Department A."


def test_parse_nbib_text__unmapped_auid_ad_are_not_read() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AD  - Department A.\n"
    )

    record = _parse_authors(text, _MAPPING)

    assert record.author_names == "Smith, John"
    assert (record.author_ids, record.author_affiliations) == (None, None)


def test_parse_nbib_text__ad_mapped_elsewhere_behaves_like_normal_tag() -> None:
    mapping = mapping_of({"FAU": "authors", "AD": "notes"}, defaults=ROW_DEFAULTS)
    text = "PMID- 1\nFAU - Smith, John\nAD  - Department A.\n"

    record = parse_nbib_text(text, mapping).rows[0].record

    assert record.notes == "Department A."
    assert record.author_affiliations is None


def test_suggest_nbib_mapping__maps_auid_and_ad_to_authors() -> None:
    assert targets_of(suggest_nbib_mapping(["FAU", "AUID", "AD"])) == {
        "FAU": "authors",
        "AUID": "authors",
        "AD": "authors",
    }


def test_parse_nbib_text__names_are_kept_as_in_the_file() -> None:
    record = _parse_authors("PMID- 1\nFAU - Agnolín, Federico L\nFAU - Madonna\n")

    assert record.author_names == "Agnolín, Federico L|Madonna"


_KEYWORD_MAPPING = suggest_nbib_mapping(["OT", "MH"])


def test_parse_nbib_text__mh_keywords_get_mesh_prefix() -> None:
    text = "PMID- 1\nMH  - *Dinosaurs/anatomy & histology\nMH  - Animals\n"

    record = parse_nbib_text(text, _KEYWORD_MAPPING).rows[0].record

    assert record.keywords == [
        "[MeSH] *Dinosaurs/anatomy & histology",
        "[MeSH] Animals",
    ]


def test_parse_nbib_text__ot_keywords_have_no_prefix() -> None:
    text = "PMID- 1\nOT  - Quality control\nMH  - Quality Control\n"

    record = parse_nbib_text(text, _KEYWORD_MAPPING).rows[0].record

    assert record.keywords == ["Quality control", "[MeSH] Quality Control"]


def test_parse_nbib_text__mh_mapped_elsewhere_has_no_prefix() -> None:
    mapping = mapping_of({"MH": "notes"}, defaults=ROW_DEFAULTS)

    record = parse_nbib_text("PMID- 1\nMH  - *Dinosaurs\n", mapping).rows[0].record

    assert record.notes == "*Dinosaurs"


def test_parse_nbib_text__mh_raw_fields_keep_original_values() -> None:
    text = "PMID- 1\nMH  - *Dinosaurs\nMH  - Animals\n"

    row = parse_nbib_text(text, _KEYWORD_MAPPING).rows[0]

    assert row.raw_fields["MH"] == "*Dinosaurs\nAnimals"


def test_suggest_nbib_mapping__maps_bti_to_journal() -> None:
    assert targets_of(suggest_nbib_mapping(["BTI"])) == {"BTI": "journal"}


def test_parse_nbib_text__bti_fills_journal() -> None:
    text = "PMID- 1\nBTI - Micro-, Meso- and Macro-Dynamics of the Brain\n"

    record = parse_nbib_text(text, suggest_nbib_mapping(["BTI"])).rows[0].record

    assert record.journal == "Micro-, Meso- and Macro-Dynamics of the Brain"


def test_parse_nbib_text__editor_ad_is_left_out() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AD  - Department A.\n"
        "FED - Doe, Jane\n"
        "AD  - Department B.\n"
    )

    assert _parse_authors(text).author_affiliations == "Department A."


def test_parse_nbib_text__editor_auid_is_left_out() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "ED  - Doe J\n"
        "AUID- ORCID: 0000-0002-6000-6450\n"
    )

    assert _parse_authors(text).author_ids is None


def test_parse_nbib_text__author_after_editor_gets_its_own_ad() -> None:
    text = (
        "PMID- 1\n"
        "FED - Doe, Jane\n"
        "AD  - Department B.\n"
        "FAU - Smith, John\n"
        "AD  - Department A.\n"
    )

    record = _parse_authors(text)

    assert record.author_names == "Smith, John"
    assert record.author_affiliations == "Department A."


def test_parse_nbib_record__keeps_is_qualifier() -> None:
    mapping = mapping_of(
        {"IS": Suggest("issn_isbn", {"kind": "issn"})}, defaults=ROW_DEFAULTS
    )

    row = parse_nbib_record([("IS", "1234-5678 (Print)")], mapping, _NBIB_SETTINGS)

    assert row.record.issn == "1234-5678 (Print)"
    assert row.raw_fields == {"IS": "1234-5678 (Print)"}


def test_parse_nbib_record__attaches_auid_and_ad_to_preceding_fau() -> None:
    mapping = mapping_of(
        {"FAU": "authors", "AUID": _IDS, "AD": _AFFILIATIONS},
        defaults=ROW_DEFAULTS,
    )
    lines = [
        ("FAU", "Smith, John"),
        ("AUID", "ORCID: 0000-0001-2345-6789"),
        ("AD", "University X"),
    ]

    row = parse_nbib_record(lines, mapping)

    assert row.record.author_names == "Smith, John"
    assert row.record.author_ids == "orcid:0000-0001-2345-6789"
    assert row.record.author_affiliations == "University X"


def _fail_on_bad_title(monkeypatch: pytest.MonkeyPatch) -> None:
    real = mapping_module.apply_mapping

    def apply(
        raw_fields: dict[str, str], mapping: FieldMapping, settings: ParseSettings
    ) -> Record:
        if "Bad" in raw_fields.values():
            raise ValueError("bad value")
        return real(raw_fields, mapping, settings)

    monkeypatch.setattr(mapping_module, "apply_mapping", apply)


def test_parse_nbib_text__skips_record_that_fails_to_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fail_on_bad_title(monkeypatch)
    text = "PMID- 1\nTI  - Good\n\nPMID- 2\nTI  - Bad\n\nPMID- 3\nTI  - Also\n"

    result = nbib.parse_nbib_text(text, mapping_of({"TI": "title"}))

    assert [row.record.title for row in result.rows] == ["Good", "Also"]
    assert [row.row_number for row in result.rows] == [1, 7]
    assert result.skipped == [SkippedRow(4, "bad value")]
