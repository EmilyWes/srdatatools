from pathlib import Path

from app.models.record import Author
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


def test_suggest_nbib_mapping__alias_overrides_replace_defaults() -> None:
    suggestions = suggest_nbib_mapping(["TA", "JT"], {"journal": ["jt"]})

    assert suggestions.targets == {"JT": "journal"}


def test_suggest_nbib_mapping__prefers_fau_over_au_for_authors() -> None:
    assert suggest_nbib_mapping(["AU", "FAU"]).targets == {"FAU": "authors"}


def test_suggest_nbib_mapping__falls_back_to_au_without_fau() -> None:
    assert suggest_nbib_mapping(["AU"]).targets == {"AU": "authors"}


def test_suggest_nbib_mapping__maps_dp_to_date_and_keywords_from_ot_and_mh() -> None:
    suggestions = suggest_nbib_mapping(["DP", "OT", "MH"])

    assert suggestions.targets == {"DP": "date", "OT": "keywords", "MH": "keywords"}


def test_suggest_nbib_mapping__routes_pmc_and_mid_to_other_ids() -> None:
    suggestions = suggest_nbib_mapping(["PMC", "MID"])

    assert suggestions.targets == {"PMC": "other_ids.pmc", "MID": "other_ids.mid"}


def test_suggest_nbib_mapping__maps_is_to_issn_and_isbn_tag_to_isbn() -> None:
    suggestions = suggest_nbib_mapping(["IS", "ISBN"])

    assert suggestions.targets == {"IS": "issn", "ISBN": "isbn"}


def test_parse_nbib_text__isbn_tag_fills_isbn() -> None:
    text = "PMID- 1\nIS  - 1234-5678 (Print)\nISBN- 978-3-16-148410-0\n"

    record = parse_nbib_text(text, suggest_nbib_mapping(["IS", "ISBN"])).rows[0].record

    assert record.issn == "1234-5678"
    assert record.isbn == "978-3-16-148410-0"


def _parse_issn(text: str) -> str | None:
    return parse_nbib_text(text, suggest_nbib_mapping(["IS"])).rows[0].record.issn


def test_parse_nbib_text__is_strips_print_electronic_qualifier() -> None:
    assert _parse_issn("PMID- 1\nIS  - 1234-5678 (Print)\n") == "1234-5678"


def test_parse_nbib_text__multiple_is_lines_prefer_electronic() -> None:
    text = (
        "PMID- 1\n"
        "IS  - 1234-5678 (Print)\n"
        "IS  - 8765-4321 (Electronic)\n"
        "IS  - 1234-5678 (Linking)\n"
    )

    assert _parse_issn(text) == "8765-4321"


def test_parse_nbib_text__multiple_is_lines_without_electronic_keep_first() -> None:
    text = "PMID- 1\nIS  - 1234-5678 (Print)\nIS  - 1111-2222 (Linking)\n"

    assert _parse_issn(text) == "1234-5678"


def test_parse_nbib_text__is_raw_fields_keep_qualifiers() -> None:
    text = "PMID- 1\nIS  - 1234-5678 (Print)\nIS  - 8765-4321 (Electronic)\n"

    row = parse_nbib_text(text, suggest_nbib_mapping(["IS"])).rows[0]

    assert row.raw_fields["IS"] == "1234-5678 (Print)\n8765-4321 (Electronic)"


def test_parse_nbib_text__is_without_qualifier_unchanged() -> None:
    assert _parse_issn("PMID- 1\nIS  - 1234-5678\n") == "1234-5678"


def test_suggest_nbib_mapping__leaves_unknown_tags_unmapped() -> None:
    assert suggest_nbib_mapping(["OWN", "STAT", "ZZ"]).targets == {}


def test_parse_nbib_file__default_mapping_on_realistic_export() -> None:
    path = NBIB_FIXTURES_DIR / "pubmed_style.nbib"

    result = parse_nbib_file(
        path, suggest_nbib_mapping(list(read_nbib_tags(path).samples))
    )

    first, second = (row.record for row in result.rows)
    assert first.pmid == "31234567"
    assert [author.full_name for author in first.authors] == [
        "Smith, John A",
        "Doe, Jane",
    ]
    assert first.pages == "100-110"
    assert first.doi == "10.1016/j.jbi.2020.1"
    assert first.other_ids == {"pmc": "PMC7000001"}
    assert first.issn == "1532-0480"
    assert first.publication_date is not None
    assert (
        first.publication_date.year,
        first.publication_date.month,
        first.publication_date.day,
    ) == (2020, 5, 14)
    assert second.keywords == ["[MeSH] Humans", "[MeSH] Review Literature as Topic"]
    assert second.publication_date is not None
    assert (second.publication_date.year, second.publication_date.month) == (2019, 1)


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


_AUTHOR_MAPPING = FieldMapping(
    targets={"FAU": "authors", "AUID": "authors", "AD": "authors"},
    list_delimiter="\n",
)


def _parse_authors(text: str, mapping: FieldMapping = _AUTHOR_MAPPING) -> list[Author]:
    return parse_nbib_text(text, mapping).rows[0].record.authors


def test_parse_nbib_text__auid_orcid_attaches_to_preceding_author() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "FAU - Doe, Jane\n"
        "AUID- ORCID: 0000-0002-6000-6450\n"
    )

    authors = _parse_authors(text)

    assert [a.orcid for a in authors] == [
        "0000-0001-8894-9875",
        "0000-0002-6000-6450",
    ]


def test_parse_nbib_text__orcid_url_prefix_is_stripped() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: https://orcid.org/0000-0001-8894-9875\n"
        "FAU - Doe, Jane\n"
        "AUID- ORCID: http://orcid.org/0000-0002-6000-6450\n"
    )

    authors = _parse_authors(text)

    assert [a.orcid for a in authors] == [
        "0000-0001-8894-9875",
        "0000-0002-6000-6450",
    ]


def test_parse_nbib_text__non_orcid_auid_goes_to_author_other_ids() -> None:
    text = "PMID- 1\nFAU - Smith, John\nAUID- ISNI: 0000 0001 2345 6789\n"

    author = _parse_authors(text)[0]

    assert author.orcid is None
    assert author.other_ids == {"isni": "0000 0001 2345 6789"}


def test_parse_nbib_text__multiple_ad_lines_become_separate_affiliations() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AD  - Department A, University X.\n"
        "AD  - Department B, University Y. smith@example.org.\n"
        "FAU - Doe, Jane\n"
        "AD  - Department C, University Z.\n"
    )

    authors = _parse_authors(text)

    assert [[aff.name for aff in a.affiliations] for a in authors] == [
        [
            "Department A, University X.",
            "Department B, University Y. smith@example.org.",
        ],
        ["Department C, University Z."],
    ]


def test_parse_nbib_text__ad_continuation_line_is_joined() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AD  - Department of Geosciences, Virginia Tech,\n"
        "      Blacksburg, VA, USA.\n"
    )

    author = _parse_authors(text)[0]

    assert author.affiliations[0].name == (
        "Department of Geosciences, Virginia Tech, Blacksburg, VA, USA."
    )


def test_parse_nbib_text__author_without_auid_or_ad_has_none() -> None:
    text = "PMID- 1\nFAU - Smith, John\nAD  - Department A.\nFAU - Doe, Jane\n"

    doe = _parse_authors(text)[1]

    assert doe.orcid is None
    assert doe.affiliations == []


def test_parse_nbib_text__auid_ad_before_first_author_are_ignored() -> None:
    text = (
        "PMID- 1\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AD  - Department A.\n"
        "FAU - Smith, John\n"
    )

    author = _parse_authors(text)[0]

    assert author.orcid is None
    assert author.affiliations == []


def test_parse_nbib_text__au_fallback_author_tag_groups_auid_ad() -> None:
    mapping = FieldMapping(
        targets={"AU": "authors", "AUID": "authors", "AD": "authors"},
        list_delimiter="\n",
    )
    text = (
        "PMID- 1\n"
        "AU  - Smith J\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AU  - Doe J\n"
        "AD  - Department A.\n"
    )

    authors = _parse_authors(text, mapping)

    assert [a.full_name for a in authors] == ["Smith J", "Doe J"]
    assert authors[0].orcid == "0000-0001-8894-9875"
    assert authors[1].affiliations[0].name == "Department A."


def test_parse_nbib_text__unmapped_auid_ad_are_not_attached() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AD  - Department A.\n"
    )

    author = _parse_authors(text, _MAPPING)[0]

    assert author.orcid is None
    assert author.affiliations == []


def test_parse_nbib_text__auid_ad_values_are_not_author_names() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AUID- ORCID: 0000-0001-8894-9875\n"
        "AD  - Department A.\n"
    )

    authors = _parse_authors(text)

    assert [a.full_name for a in authors] == ["Smith, John"]


def test_parse_nbib_text__ad_mapped_elsewhere_behaves_like_normal_tag() -> None:
    mapping = FieldMapping(
        targets={"FAU": "authors", "AD": "notes"}, list_delimiter="\n"
    )
    text = "PMID- 1\nFAU - Smith, John\nAD  - Department A.\n"

    record = parse_nbib_text(text, mapping).rows[0].record

    assert record.notes == "Department A."
    assert record.authors[0].affiliations == []


def test_suggest_nbib_mapping__maps_auid_and_ad_to_authors() -> None:
    assert suggest_nbib_mapping(["FAU", "AUID", "AD"]).targets == {
        "FAU": "authors",
        "AUID": "authors",
        "AD": "authors",
    }


def test_parse_nbib_text__fau_is_split_into_family_and_given_name() -> None:
    author = _parse_authors("PMID- 1\nFAU - Agnolín, Federico L\n")[0]

    assert (author.family_name, author.given_name) == ("Agnolín", "Federico L")
    assert author.full_name == "Agnolín, Federico L"


def test_parse_nbib_text__fau_suffix_stays_in_given_name() -> None:
    author = _parse_authors("PMID- 1\nFAU - Smith, John A Jr\n")[0]

    assert (author.family_name, author.given_name) == ("Smith", "John A Jr")


def test_parse_nbib_text__name_without_comma_is_not_split() -> None:
    author = _parse_authors("PMID- 1\nFAU - Madonna\n")[0]

    assert (author.family_name, author.given_name) == (None, None)
    assert author.full_name == "Madonna"


def test_parse_nbib_text__au_fallback_name_is_not_split() -> None:
    mapping = FieldMapping(targets={"AU": "authors"}, list_delimiter="\n")

    author = _parse_authors("PMID- 1\nAU  - Müller RT\n", mapping)[0]

    assert (author.family_name, author.given_name) == (None, None)
    assert author.full_name == "Müller RT"


_KEYWORD_MAPPING = FieldMapping(
    targets={"OT": "keywords", "MH": "keywords"}, list_delimiter="\n"
)


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
    mapping = FieldMapping(targets={"MH": "notes"}, list_delimiter="\n")

    record = parse_nbib_text("PMID- 1\nMH  - *Dinosaurs\n", mapping).rows[0].record

    assert record.notes == "*Dinosaurs"


def test_parse_nbib_text__mh_raw_fields_keep_original_values() -> None:
    text = "PMID- 1\nMH  - *Dinosaurs\nMH  - Animals\n"

    row = parse_nbib_text(text, _KEYWORD_MAPPING).rows[0]

    assert row.raw_fields["MH"] == "*Dinosaurs\nAnimals"


def test_suggest_nbib_mapping__maps_bti_to_journal() -> None:
    assert suggest_nbib_mapping(["BTI"]).targets == {"BTI": "journal"}


def test_parse_nbib_text__bti_fills_journal() -> None:
    text = "PMID- 1\nBTI - Micro-, Meso- and Macro-Dynamics of the Brain\n"

    record = parse_nbib_text(text, suggest_nbib_mapping(["BTI"])).rows[0].record

    assert record.journal == "Micro-, Meso- and Macro-Dynamics of the Brain"


def test_parse_nbib_text__editor_ad_after_author_is_not_attached() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "AD  - Department A.\n"
        "FED - Doe, Jane\n"
        "AD  - Department B.\n"
    )

    author = _parse_authors(text)[0]

    assert [a.name for a in author.affiliations] == ["Department A."]


def test_parse_nbib_text__editor_auid_is_not_attached() -> None:
    text = (
        "PMID- 1\n"
        "FAU - Smith, John\n"
        "ED  - Doe J\n"
        "AUID- ORCID: 0000-0002-6000-6450\n"
    )

    assert _parse_authors(text)[0].orcid is None


def test_parse_nbib_text__author_after_editor_gets_its_own_ad() -> None:
    text = (
        "PMID- 1\n"
        "FED - Doe, Jane\n"
        "AD  - Department B.\n"
        "FAU - Smith, John\n"
        "AD  - Department A.\n"
    )

    authors = _parse_authors(text)

    assert [a.full_name for a in authors] == ["Smith, John"]
    assert [a.name for a in authors[0].affiliations] == ["Department A."]
