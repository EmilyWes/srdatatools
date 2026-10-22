import csv
from io import StringIO

import pytest

from app.models.record import Affiliation, Author, Record
from app.parsers.bibtex import parse_bibtex_text, suggest_bibtex_mapping
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.scopus import SCOPUS
from app.parsers.ris import parse_ris_text, suggest_ris_mapping

_CSV_PROFILE = SCOPUS.formats["csv"]
_RIS_PROFILE = SCOPUS.formats["ris"]
_BIBTEX_PROFILE = SCOPUS.formats["bibtex"]


def _suggest_csv(headers: list[str]) -> FieldMapping:
    return suggest_mapping(headers, _CSV_PROFILE.aliases, _CSV_PROFILE.ignored_keys)


def _csv_text(row: dict[str, str]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()


def _parse_csv(row: dict[str, str], mapping: FieldMapping | None = None) -> Record:
    mapping = mapping or _suggest_csv(list(row))
    result = apply_profile(parse_csv_text(_csv_text(row), mapping), _CSV_PROFILE)
    return result.rows[0].record


_AUTHOR_ROW = {
    "Authors": "Teng Y.; Han Y.",
    "Author full names": "Teng, Yu (60652739200); Han, Yiyong (59534195400)",
    "Author(s) ID": "60652739200; 59534195400",
    "Authors with affiliations": (
        "Teng Y., Guangxi Cartier Technology Ltd., Nanning, China; "
        "Han Y., Nanning University, Guangxi, China"
    ),
}


def test_scopus_csv__suggests_all_author_columns_as_authors() -> None:
    mapping = _suggest_csv(list(_AUTHOR_ROW))

    assert mapping.targets == {header: "authors" for header in _AUTHOR_ROW}


def test_scopus_csv__ignores_conference_details_and_publication_stage() -> None:
    headers = [
        "Conference name",
        "Conference date",
        "Conference location",
        "Conference code",
        "Document Type",
        "Publication Stage",
    ]

    mapping = _suggest_csv(headers)

    assert mapping.targets == {
        "Conference name": "conference_name",
        "Document Type": "publication_type",
    }


def test_scopus_csv__zips_author_columns_by_position() -> None:
    record = _parse_csv(_AUTHOR_ROW)

    assert record.authors == [
        Author(
            full_name="Teng, Yu",
            family_name="Teng",
            given_name="Yu",
            other_ids={"scopus_author_id": "60652739200"},
            affiliations=[
                Affiliation(name="Guangxi Cartier Technology Ltd., Nanning, China")
            ],
        ),
        Author(
            full_name="Han, Yiyong",
            family_name="Han",
            given_name="Yiyong",
            other_ids={"scopus_author_id": "59534195400"},
            affiliations=[Affiliation(name="Nanning University, Guangxi, China")],
        ),
    ]


def test_scopus_csv__abbreviated_names_and_id_column_without_full_names() -> None:
    record = _parse_csv(
        {"Authors": "Teng Y.; Han Y.", "Author(s) ID": "60652739200; 59534195400"}
    )

    assert record.authors == [
        Author(full_name="Teng Y.", other_ids={"scopus_author_id": "60652739200"}),
        Author(full_name="Han Y.", other_ids={"scopus_author_id": "59534195400"}),
    ]


def test_scopus_csv__author_without_affiliation_gets_none() -> None:
    record = _parse_csv(
        {
            "Author full names": "Teng, Yu (60652739200); Han, Yiyong (59534195400)",
            "Authors with affiliations": "Teng Y., Nanning University; Han Y.",
        }
    )

    assert record.authors[0].affiliations == [Affiliation(name="Nanning University")]
    assert record.authors[1].affiliations == []


def test_scopus_csv__mismatched_column_is_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = {
        "Author full names": "Teng, Yu; Han, Yiyong",
        "Author(s) ID": "60652739200",
    }

    with caplog.at_level("WARNING"):
        record = _parse_csv(row)

    assert [author.full_name for author in record.authors] == [
        "Teng, Yu",
        "Han, Yiyong",
    ]
    assert all(author.other_ids == {} for author in record.authors)
    assert "Author(s) ID" in caplog.text


def test_scopus_csv__unmapped_authors_stay_empty() -> None:
    record = _parse_csv(_AUTHOR_ROW, FieldMapping(targets={}))

    assert record.authors == []


def test_scopus_csv__prefixes_author_keywords_only() -> None:
    record = _parse_csv(
        {
            "Author Keywords": "ANSYS Simulation; Battery Thermal Management",
            "Index Keywords": "Bionics; Thermal",
        }
    )

    assert record.keywords == [
        "[Author] ANSYS Simulation",
        "[Author] Battery Thermal Management",
        "Bionics",
        "Thermal",
    ]


def test_scopus_csv__unmapped_keywords_stay_empty() -> None:
    row = {"Author Keywords": "ANSYS Simulation", "Index Keywords": "Bionics"}

    record = _parse_csv(row, FieldMapping(targets={}))

    assert record.keywords == []


def test_scopus_csv__maps_eid_and_pubmed_id() -> None:
    record = _parse_csv({"EID": "2-s2.0-105040180364", "PubMed ID": "32161388"})

    assert record.other_ids == {"eid": "2-s2.0-105040180364"}
    assert record.pmid == "32161388"


def test_scopus_csv__matches_header_with_eid() -> None:
    assert _CSV_PROFILE.matches('"Authors","Title","EID"\n"A","T","2-s2.0-1"\n')


def test_scopus_csv__does_not_match_header_without_eid() -> None:
    assert not _CSV_PROFILE.matches("PMID,Title,Citation,Journal/Book\n1,A,B,C\n")


def _parse_ris(body: str) -> Record:
    text = f"TY  - JOUR\n{body}ER  - \n"
    tags = list(dict.fromkeys(line[:2] for line in text.splitlines()))
    mapping = suggest_ris_mapping(tags, _RIS_PROFILE.aliases)
    result = apply_profile(parse_ris_text(text, mapping), _RIS_PROFILE)
    return result.rows[0].record


def test_scopus_ris__publication_type_from_m3_not_ty() -> None:
    mapping = suggest_ris_mapping(["TY", "M3"], _RIS_PROFILE.aliases)

    assert mapping.targets == {"M3": "publication_type"}


def test_scopus_ris__document_type_and_pmid() -> None:
    record = _parse_ris("M3  - Retracted\nC2  - 32161388\n")

    assert record.publication_type == "Retracted"
    assert record.pmid == "32161388"


def test_scopus_ris__takes_eid_and_conference_name_from_notes() -> None:
    notes = (
        "N1  - EID: 2-s2.0-105040180364\nN1  - Cited By: 0\n"
        "N1  - Conference name: 5th Conference on Control Engineering\n"
    )

    record = _parse_ris(notes)

    assert record.other_ids == {"eid": "2-s2.0-105040180364"}
    assert record.conference_name == "5th Conference on Control Engineering"
    assert record.notes == (
        "EID: 2-s2.0-105040180364\nCited By: 0\n"
        "Conference name: 5th Conference on Control Engineering"
    )


def test_scopus_ris__record_without_labelled_notes_is_unchanged() -> None:
    record = _parse_ris("TI  - Some Paper\nN1  - Export Date: 22 October 2026\n")

    assert record.other_ids == {}
    assert record.conference_name is None


def test_scopus_ris__matches_db_line() -> None:
    assert _RIS_PROFILE.matches("TY  - JOUR\nTI  - T\nDB  - Scopus\nER  - \n")


def test_scopus_ris__does_not_match_without_db_line() -> None:
    assert not _RIS_PROFILE.matches("TY  - JOUR\nTI  - Scopus\nER  - \n")


def _parse_bibtex(fields: str, mapping: FieldMapping | None = None) -> Record:
    text = f"@ARTICLE{{key1,\n{fields}}}\n"
    if mapping is None:
        keys = [
            "@type",
            "@key",
            *(line.split("=")[0].strip() for line in fields.splitlines()),
        ]
        mapping = suggest_bibtex_mapping(keys, _BIBTEX_PROFILE.aliases)
    result = apply_profile(parse_bibtex_text(text, mapping), _BIBTEX_PROFILE)
    return result.rows[0].record


def test_scopus_bibtex__suggests_scopus_fields() -> None:
    keys = ["@type", "type", "pmid", "author_keywords", "keywords"]

    mapping = suggest_bibtex_mapping(keys, _BIBTEX_PROFILE.aliases)

    assert mapping.targets == {
        "type": "publication_type",
        "pmid": "pmid",
        "author_keywords": "keywords",
        "keywords": "keywords",
    }


def test_scopus_bibtex__document_type_and_pmid() -> None:
    record = _parse_bibtex("type = {Erratum},\npmid = {41826489},\n")

    assert record.publication_type == "Erratum"
    assert record.pmid == "41826489"


def test_scopus_bibtex__prefixes_cleaned_author_keywords_only() -> None:
    record = _parse_bibtex(
        'author_keywords = {Gr{\\"o}nland; Asia},\nkeywords = {R\\&D; Thermal},\n'
    )

    assert record.keywords == ["[Author] Grönland", "[Author] Asia", "R&D", "Thermal"]


def test_scopus_bibtex__unmapped_keywords_stay_empty() -> None:
    record = _parse_bibtex(
        "author_keywords = {Asia},\nkeywords = {Thermal},\n", FieldMapping(targets={})
    )

    assert record.keywords == []


@pytest.mark.parametrize(
    "url",
    [
        "https://www.scopus.com/pages/publications/105040180364?origin=resultslist",
        "https://www.scopus.com/inward/record.uri?eid=2-s2.0-105040180364&partnerID=40",
    ],
)
def test_scopus_bibtex__eid_from_url(url: str) -> None:
    record = _parse_bibtex(f"url = {{{url}}},\n")

    assert record.other_ids == {"eid": "2-s2.0-105040180364"}


def test_scopus_bibtex__non_scopus_url_gives_no_eid() -> None:
    record = _parse_bibtex("url = {https://example.org/publications/123},\n")

    assert record.other_ids == {}


def test_scopus_bibtex__matches_source_field() -> None:
    assert _BIBTEX_PROFILE.matches(
        "@ARTICLE{k,\n\ttitle = {T},\n\tsource = {Scopus},\n}\n"
    )


def test_scopus_bibtex__does_not_match_without_source_field() -> None:
    assert not _BIBTEX_PROFILE.matches("@ARTICLE{k,\n\ttitle = {Scopus}\n}\n")
