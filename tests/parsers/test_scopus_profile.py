import csv
from io import StringIO

import pytest

from app.models.record import Affiliation, Author, Record
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.scopus import SCOPUS

_CSV_PROFILE = SCOPUS.formats["csv"]


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
