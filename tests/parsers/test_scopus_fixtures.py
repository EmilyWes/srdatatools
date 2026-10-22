from pathlib import Path

import pytest

from app.models.record import Record
from app.parsers.bibtex import (
    parse_bibtex_file,
    read_bibtex_fields,
    suggest_bibtex_mapping,
)
from app.parsers.common import ParseResult
from app.parsers.csv_ import parse_csv_file, read_csv_headers, suggest_mapping
from app.parsers.detect import detect_source
from app.parsers.profiles import apply_profile
from app.parsers.profiles.scopus import SCOPUS
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping
from tests.vendor_data import vendor_file, vendor_files

_FORMAT_BY_SUFFIX = {".csv": "csv", ".ris": "ris", ".bib": "bibtex"}

_HUMMINGBIRD_EID = "2-s2.0-85081690252"
_NODOSAUR_EID = "2-s2.0-105050698470"
_CONFERENCE_EID = "2-s2.0-105040180364"


def _parse(path: Path, file_format: str) -> ParseResult:
    profile = SCOPUS.formats[file_format]
    if file_format == "csv":
        headers = list(read_csv_headers(path).samples)
        mapping = suggest_mapping(headers, profile.aliases, profile.ignored_keys)
        return apply_profile(parse_csv_file(path, mapping), profile)
    if file_format == "ris":
        tags = list(read_ris_tags(path).samples)
        mapping = suggest_ris_mapping(tags, profile.aliases)
        return apply_profile(parse_ris_file(path, mapping), profile)
    keys = list(read_bibtex_fields(path).samples)
    mapping = suggest_bibtex_mapping(keys, profile.aliases)
    return apply_profile(parse_bibtex_file(path, mapping), profile)


def _records_by_eid(suffix: str) -> dict[str, Record]:
    result = _parse(vendor_file("scopus", "small", suffix), _FORMAT_BY_SUFFIX[suffix])
    assert result.skipped == []
    assert len(result.rows) == 10
    return {row.record.other_ids["eid"]: row.record for row in result.rows}


@pytest.fixture
def csv_records() -> dict[str, Record]:
    return _records_by_eid(".csv")


@pytest.fixture
def ris_records() -> dict[str, Record]:
    return _records_by_eid(".ris")


@pytest.fixture
def bibtex_records() -> dict[str, Record]:
    return _records_by_eid(".bib")


@pytest.mark.parametrize("suffix", list(_FORMAT_BY_SUFFIX))
def test_scopus_small__detects_scopus_source(suffix: str) -> None:
    path = vendor_file("scopus", "small", suffix)

    assert detect_source(path, _FORMAT_BY_SUFFIX[suffix]) == "scopus"


def test_scopus_small_csv__zips_author_columns(
    csv_records: dict[str, Record],
) -> None:
    authors = csv_records[_NODOSAUR_EID].authors

    oyabu = authors[0]
    assert (oyabu.family_name, oyabu.given_name) == ("Oyabu", "Shumpei")
    assert oyabu.other_ids == {"scopus_author_id": "60900075400"}
    assert [a.name for a in oyabu.affiliations] == [
        "Department of Natural History and Planetary Sciences, Hokkaido University, "
        "Kita 10, Nishi 8, Kita-ku, Hokkaido, Sapporo, 060-0810, Japan"
    ]
    assert all(author.other_ids for author in authors)


def test_scopus_small_csv__prefixes_author_keywords(
    csv_records: dict[str, Record],
) -> None:
    keywords = csv_records[_CONFERENCE_EID].keywords

    assert "[Author] ANSYS Simulation" in keywords
    assert "Balancing" in keywords


def test_scopus_small_ris__applies_profile_fixes(
    ris_records: dict[str, Record],
) -> None:
    hummingbird = ris_records[_HUMMINGBIRD_EID]
    assert hummingbird.pmid == "32161388"
    assert hummingbird.issn == "00280836"
    assert hummingbird.publication_type == "Retracted"
    conference = ris_records[_CONFERENCE_EID]
    assert conference.isbn == "979-840072171-7"
    assert conference.issn is None
    assert conference.conference_name == (
        "5th International Conference on Computer, Artificial Intelligence and "
        "Control Engineering, CAICE 2026"
    )


def test_scopus_small_bibtex__applies_profile_fixes(
    bibtex_records: dict[str, Record],
) -> None:
    hummingbird = bibtex_records[_HUMMINGBIRD_EID]
    assert hummingbird.pmid == "32161388"
    assert hummingbird.publication_type == "Retracted"
    assert "[Author] ANSYS Simulation" in bibtex_records[_CONFERENCE_EID].keywords


def test_scopus_small__formats_agree_on_ids_and_document_type(
    csv_records: dict[str, Record],
    ris_records: dict[str, Record],
    bibtex_records: dict[str, Record],
) -> None:
    assert csv_records.keys() == ris_records.keys() == bibtex_records.keys()
    for eid, record in csv_records.items():
        for other in (ris_records[eid], bibtex_records[eid]):
            assert other.doi == record.doi, eid
            assert other.pmid == record.pmid, eid
            assert other.publication_type == record.publication_type, eid


@pytest.mark.big
def test_scopus_big__every_file_parses_without_skips() -> None:
    for path in vendor_files("scopus", "big"):
        if path.suffix.lower() not in _FORMAT_BY_SUFFIX:
            continue
        result = _parse(path, _FORMAT_BY_SUFFIX[path.suffix.lower()])
        assert result.rows, path.name
        assert result.skipped == [], path.name
