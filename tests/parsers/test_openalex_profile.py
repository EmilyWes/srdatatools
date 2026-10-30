import csv
from dataclasses import replace
from io import StringIO

import pytest

from app.models.record import Affiliation, Author, Record
from app.parsers.bibtex import parse_bibtex_text, suggest_bibtex_mapping
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.openalex import OPENALEX
from app.parsers.ris import parse_ris_text, suggest_ris_mapping

_CSV_PROFILE = OPENALEX.formats["csv"]
_RIS_PROFILE = OPENALEX.formats["ris"]
_BIBTEX_PROFILE = OPENALEX.formats["bibtex"]


def _suggest_csv(headers: list[str]) -> FieldMapping:
    mapping = suggest_mapping(headers, _CSV_PROFILE.aliases, _CSV_PROFILE.ignored_keys)
    assert _CSV_PROFILE.list_delimiter is not None
    return replace(mapping, list_delimiter=_CSV_PROFILE.list_delimiter)


def _csv_text(row: dict[str, str]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()


def _parse_csv(row: dict[str, str], mapping: FieldMapping | None = None) -> Record:
    mapping = mapping or _suggest_csv(list(row))
    result = apply_profile(
        parse_csv_text(_csv_text(row), mapping), _CSV_PROFILE, mapping
    )
    return result.rows[0].record


_AUTHOR_ROW = {
    "Author": "Matthew G. Baron|DAVID B. NORMAN|Paul M. Barrett",
    "Author IDs": "A5091833725|A5085682707|A5053220301",
    "ORCID": "https://orcid.org/0000-0001-9069-7638||https://orcid.org/0000-0003-0412-3000",
}


def _without(mapping: FieldMapping, *ignored: str) -> FieldMapping:
    targets = {k: t for k, t in mapping.targets.items() if k not in ignored}
    return replace(mapping, targets=targets)


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

    assert mapping.targets == {
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
        "Work ID": "other_ids.openalex",
        "Type": "publication_type",
    }


def test_openalex_csv__zips_author_ids_and_orcids_by_position() -> None:
    record = _parse_csv(_AUTHOR_ROW)

    assert record.authors == [
        Author(
            full_name="Matthew G. Baron",
            orcid="0000-0001-9069-7638",
            other_ids={"openalex_author_id": "A5091833725"},
        ),
        Author(
            full_name="DAVID B. NORMAN",
            other_ids={"openalex_author_id": "A5085682707"},
        ),
        Author(
            full_name="Paul M. Barrett",
            orcid="0000-0003-0412-3000",
            other_ids={"openalex_author_id": "A5053220301"},
        ),
    ]


def test_openalex_csv__mismatched_column_is_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = {**_AUTHOR_ROW, "ORCID": "https://orcid.org/0000-0001-9069-7638"}

    with caplog.at_level("WARNING"):
        record = _parse_csv(row)

    assert all(author.orcid is None for author in record.authors)
    assert [a.other_ids["openalex_author_id"] for a in record.authors] == [
        "A5091833725",
        "A5085682707",
        "A5053220301",
    ]
    assert "ORCID" in caplog.text


def test_openalex_csv__empty_id_columns_leave_authors_bare() -> None:
    record = _parse_csv({"Author": "Robert T. Bakker", "Author IDs": "", "ORCID": ""})

    assert record.authors == [Author(full_name="Robert T. Bakker")]


def test_openalex_csv__unmapped_authors_stay_empty() -> None:
    record = _parse_csv(_AUTHOR_ROW, FieldMapping(targets={}))

    assert record.authors == []


def test_openalex_csv__ignored_orcid_column_is_not_used() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "ORCID")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert all(author.orcid is None for author in record.authors)
    assert record.authors[0].other_ids == {"openalex_author_id": "A5091833725"}


def test_openalex_csv__ignored_author_ids_column_is_not_used() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "Author IDs")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert all(author.other_ids == {} for author in record.authors)
    assert record.authors[0].orcid == "0000-0001-9069-7638"


def test_openalex_csv__ignored_names_fall_back_to_orcid_for_author_count() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "Author")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert record.authors == [
        Author(
            orcid="0000-0001-9069-7638",
            other_ids={"openalex_author_id": "A5091833725"},
        ),
        Author(other_ids={"openalex_author_id": "A5085682707"}),
        Author(
            orcid="0000-0003-0412-3000",
            other_ids={"openalex_author_id": "A5053220301"},
        ),
    ]


def test_openalex_csv__only_author_ids_mapped_gives_id_only_authors() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "Author", "ORCID")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert [author.other_ids for author in record.authors] == [
        {"openalex_author_id": "A5091833725"},
        {"openalex_author_id": "A5085682707"},
        {"openalex_author_id": "A5053220301"},
    ]
    assert all(a.full_name is None and a.orcid is None for a in record.authors)


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


def test_openalex_csv__keeps_first_issn() -> None:
    record = _parse_csv({"ISSN": "0028-0836|1476-4687"})

    assert record.issn == "0028-0836"


def test_openalex_csv__strips_pubmed_url_from_pmid() -> None:
    record = _parse_csv({"PMID": "https://pubmed.ncbi.nlm.nih.gov/28332513"})

    assert record.pmid == "28332513"


def test_openalex_csv__work_id_goes_to_other_ids() -> None:
    record = _parse_csv({"Work ID": "W2601753892"})

    assert record.other_ids == {"openalex": "W2601753892"}


def test_openalex_csv__matches_work_id_and_concept_ids_headers() -> None:
    assert _CSV_PROFILE.matches("Title,Concept IDs,Work ID\nA,C1,W1\n")
    assert not _CSV_PROFILE.matches("Title,Work ID\nA,W1\n")


def test_openalex_ris__attaches_c1_affiliations_to_authors() -> None:
    text = (
        "TY  - JOUR\nAU  - Baron, Matthew\nC1  - Natural History Museum\n"
        "AU  - Norman, David\nC1  - University of Cambridge\nER  - \n"
    )
    mapping = suggest_ris_mapping(["TY", "AU", "C1"], _RIS_PROFILE.aliases)

    record = (
        apply_profile(parse_ris_text(text, mapping), _RIS_PROFILE, mapping)
        .rows[0]
        .record
    )

    assert record.authors == [
        Author(
            full_name="Baron, Matthew",
            affiliations=[Affiliation(name="Natural History Museum")],
        ),
        Author(
            full_name="Norman, David",
            affiliations=[Affiliation(name="University of Cambridge")],
        ),
    ]


def test_openalex_ris__never_matches() -> None:
    assert not _RIS_PROFILE.matches("TY  - JOUR\nTI  - A\nER  - \n")


def test_openalex_bibtex__splits_keywords_on_comma() -> None:
    text = "@article{baron2017new,\n  keywords = {dinosaur phylogeny, Ornithischia}\n}"
    mapping = suggest_bibtex_mapping(["keywords"], _BIBTEX_PROFILE.aliases)
    assert _BIBTEX_PROFILE.list_delimiter is not None
    mapping = replace(mapping, list_delimiter=_BIBTEX_PROFILE.list_delimiter)

    result = apply_profile(parse_bibtex_text(text, mapping), _BIBTEX_PROFILE, mapping)

    assert result.rows[0].record.keywords == ["dinosaur phylogeny", "Ornithischia"]


def test_openalex_bibtex__never_matches() -> None:
    assert not _BIBTEX_PROFILE.matches("@article{a,\n  title = {A},\n}\n")
