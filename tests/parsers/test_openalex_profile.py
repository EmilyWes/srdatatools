import csv
from io import StringIO

import pytest

from app.models.record import Record
from app.parsers.bibtex import parse_bibtex_text, suggest_bibtex_mapping
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.openalex import OPENALEX
from app.parsers.ris import parse_ris_text, suggest_ris_mapping
from tests.mappings import targets_of

_CSV_PROFILE = OPENALEX.formats["csv"]
_RIS_PROFILE = OPENALEX.formats["ris"]
_BIBTEX_PROFILE = OPENALEX.formats["bibtex"]


def _suggest_csv(headers: list[str]) -> FieldMapping:
    return suggest_mapping(
        headers,
        _CSV_PROFILE.suggestions,
        _CSV_PROFILE.row_defaults,
        _CSV_PROFILE.ignored_keys,
    )


def _csv_text(row: dict[str, str]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()


def _parse_csv(row: dict[str, str], mapping: FieldMapping | None = None) -> Record:
    mapping = mapping or _suggest_csv(list(row))
    result = parse_csv_text(_csv_text(row), mapping, settings=_CSV_PROFILE.settings)
    return result.rows[0].record


_AUTHOR_ROW = {
    "Author": "Matthew G. Baron|DAVID B. NORMAN|Paul M. Barrett",
    "Author IDs": "A5091833725|A5085682707|A5053220301",
    "ORCID": "https://orcid.org/0000-0001-9069-7638||https://orcid.org/0000-0003-0412-3000",
}


def _without(mapping: FieldMapping, *ignored: str) -> FieldMapping:
    return FieldMapping(
        rows={k: row for k, row in mapping.rows.items() if k not in ignored}
    )


def test_openalex_csv__suggests_only_exact_columns() -> None:
    headers = [
        "Title",
        "Author",
        "Author IDs",
        "Keyword",
        "Keyword IDs",
        "Concept",
        "Concept IDs",
        "Topic",
        "Topic IDs",
        "Source",
        "Source IDs",
        "OA source",
        "OA published",
        "Abstract",
        "Has abstract",
        "PMID",
        "PubMed",
        "ORCID",
        "Has ORCID",
        "ROR ID",
        "Work ID",
        "Type",
    ]

    mapping = _suggest_csv(headers)

    assert targets_of(mapping) == {
        "Title": "title",
        "Author": "authors",
        "Author IDs": "authors",
        "ORCID": "authors",
        "Keyword": "keywords",
        "Concept": "keywords",
        "Topic": "keywords",
        "Source": "journal",
        "Abstract": "abstract",
        "PMID": "pmid",
        "Work ID": "other_ids",
        "Type": "publication_type",
    }


_IDS = (
    "openalex_author_id:A5091833725, orcid:0000-0001-9069-7638"
    "|openalex_author_id:A5085682707"
    "|openalex_author_id:A5053220301, orcid:0000-0003-0412-3000"
)


def test_openalex_csv__keeps_names_and_groups_ids_per_author() -> None:
    record = _parse_csv(_AUTHOR_ROW)

    assert record.author_names == "Matthew G. Baron|DAVID B. NORMAN|Paul M. Barrett"
    assert record.author_ids == _IDS


def test_openalex_csv__mismatched_column_is_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = {**_AUTHOR_ROW, "ORCID": "https://orcid.org/0000-0001-9069-7638"}

    with caplog.at_level("WARNING"):
        record = _parse_csv(row)

    assert record.author_ids == (
        "openalex_author_id:A5091833725"
        "|openalex_author_id:A5085682707"
        "|openalex_author_id:A5053220301"
    )
    assert "ORCID" in caplog.text


def test_openalex_csv__empty_id_columns_leave_no_ids() -> None:
    record = _parse_csv({"Author": "Robert T. Bakker", "Author IDs": "", "ORCID": ""})

    assert (record.author_names, record.author_ids) == ("Robert T. Bakker", None)


def test_openalex_csv__unmapped_authors_stay_empty() -> None:
    record = _parse_csv(_AUTHOR_ROW, FieldMapping())

    assert (record.author_names, record.author_ids) == (None, None)


def test_openalex_csv__ignored_orcid_column_is_not_used() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "ORCID")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert record.author_ids == (
        "openalex_author_id:A5091833725"
        "|openalex_author_id:A5085682707"
        "|openalex_author_id:A5053220301"
    )


def test_openalex_csv__ignored_names_still_give_ids() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "Author")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert (record.author_names, record.author_ids) == (None, _IDS)


def test_openalex_csv__ignored_concept_column_adds_no_concepts() -> None:
    row = {"Keyword": "dinosaurs", "Concept": "Biology", "Topic": "Paleontology"}
    mapping = _without(_suggest_csv(list(row)), "Concept")

    record = _parse_csv(row, mapping)

    assert record.keywords == ["dinosaurs", "[Topic] Paleontology"]


def test_openalex_csv__prefixes_concept_and_topic_keywords() -> None:
    record = _parse_csv(
        {
            "Keyword": "dinosaurs|dinosaur paleontology",
            "Concept": "Biology|Geology",
            "Topic": "Paleontology and Evolutionary Biology",
        }
    )

    assert record.keywords == [
        "dinosaurs",
        "dinosaur paleontology",
        "[Concept] Biology",
        "[Concept] Geology",
        "[Topic] Paleontology and Evolutionary Biology",
    ]


def test_openalex_csv__work_id_goes_to_other_ids() -> None:
    record = _parse_csv({"Work ID": "W2601753892"})

    assert record.other_ids == {"openalex": "W2601753892"}


def test_openalex_csv__matches_work_id_and_concept_ids_headers() -> None:
    assert _CSV_PROFILE.matches("Title,Concept IDs,Work ID\nA,C1,W1\n")
    assert not _CSV_PROFILE.matches("Title,Work ID\nA,W1\n")


def test_openalex_ris__joins_au_and_c1_lines() -> None:
    text = (
        "TY  - JOUR\nAU  - Baron, Matthew\nC1  - Natural History Museum\n"
        "AU  - Norman, David\nC1  - University of Cambridge\nER  - \n"
    )
    mapping = suggest_ris_mapping(
        ["TY", "AU", "C1"], _RIS_PROFILE.suggestions, _RIS_PROFILE.row_defaults
    )

    record = (
        parse_ris_text(text, mapping, settings=_RIS_PROFILE.settings).rows[0].record
    )

    assert record.author_names == "Baron, Matthew|Norman, David"
    assert record.author_affiliations == (
        "Natural History Museum|University of Cambridge"
    )


def test_openalex_ris__never_matches() -> None:
    assert not _RIS_PROFILE.matches("TY  - JOUR\nTI  - A\nER  - \n")


def test_openalex_bibtex__splits_keywords_on_comma() -> None:
    text = "@article{baron2017new,\n  keywords = {dinosaur phylogeny, Ornithischia}\n}"
    mapping = suggest_bibtex_mapping(
        ["keywords"], _BIBTEX_PROFILE.suggestions, _BIBTEX_PROFILE.row_defaults
    )

    result = parse_bibtex_text(text, mapping, settings=_BIBTEX_PROFILE.settings)

    assert result.rows[0].record.keywords == ["dinosaur phylogeny", "Ornithischia"]


def test_openalex_bibtex__never_matches() -> None:
    assert not _BIBTEX_PROFILE.matches("@article{a,\n  title = {A},\n}\n")
