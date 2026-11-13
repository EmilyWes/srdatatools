from pathlib import Path

import pytest

from app.models.record import Record
from app.parsers.bibtex import (
    parse_bibtex_file,
    read_bibtex_fields,
    suggest_bibtex_mapping,
)
from app.parsers.common import FileType, ParseResult
from app.parsers.csv_ import parse_csv_file, read_csv_headers, suggest_mapping
from app.parsers.detect import detect_source
from app.parsers.profiles.scopus import SCOPUS
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping
from tests.vendor_data import vendor_file, vendor_files

_FORMAT_BY_SUFFIX: dict[str, FileType] = {
    ".csv": "csv",
    ".ris": "ris",
    ".bib": "bibtex",
}

_HUMMINGBIRD_EID = "2-s2.0-85081690252"
_NODOSAUR_EID = "2-s2.0-105050698470"
_CONFERENCE_EID = "2-s2.0-105040180364"


def _parse(path: Path, file_format: FileType) -> ParseResult:
    profile = SCOPUS.formats[file_format]
    if file_format == "csv":
        headers = list(read_csv_headers(path).samples)
        mapping = suggest_mapping(headers, profile.suggestions, profile.ignored_keys)
        return parse_csv_file(path, mapping, settings=profile.settings)
    if file_format == "ris":
        tags = list(read_ris_tags(path).samples)
        mapping = suggest_ris_mapping(tags, profile.suggestions, profile.ignored_keys)
        return parse_ris_file(path, mapping, settings=profile.settings)
    keys = list(read_bibtex_fields(path).samples)
    mapping = suggest_bibtex_mapping(keys, profile.suggestions, profile.ignored_keys)
    return parse_bibtex_file(path, mapping, settings=profile.settings)


def _records(suffix: str) -> list[Record]:
    result = _parse(vendor_file("scopus", "small", suffix), _FORMAT_BY_SUFFIX[suffix])
    assert result.skipped == []
    assert len(result.rows) == 10
    return [row.record for row in result.rows]


def _records_by_eid(suffix: str) -> dict[str, Record]:
    """Only the CSV has an EID column; the exports list the records in the same
    order."""
    eids = [record.other_ids["eid"] for record in _records(".csv")]
    return dict(zip(eids, _records(suffix), strict=True))


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


def test_scopus_small_csv__keeps_author_columns_as_in_the_file(
    csv_records: dict[str, Record],
) -> None:
    record = csv_records[_NODOSAUR_EID]

    assert (record.author_names or "").startswith("Oyabu, Shumpei (60900075400); ")
    assert (record.author_ids or "").startswith("scopus_author_id:[60900075400; ")
    assert (record.author_affiliations or "").startswith(
        "Oyabu S., Department of Natural History and Planetary Sciences, "
        "Hokkaido University, Kita 10, Nishi 8, Kita-ku, Hokkaido, Sapporo, "
        "060-0810, Japan;"
    )


def test_scopus_small_csv__keys_author_keywords_by_prefix(
    csv_records: dict[str, Record],
) -> None:
    keywords = csv_records[_CONFERENCE_EID].keywords

    assert keywords[0].startswith("Author:[ANSYS Simulation; ")
    assert keywords[1].startswith("keywords:[")


def test_scopus_small_ris__keeps_values_as_in_the_file(
    ris_records: dict[str, Record],
) -> None:
    hummingbird = ris_records[_HUMMINGBIRD_EID]
    assert hummingbird.pmid == "32161388"
    assert hummingbird.issn == "00280836 (ISSN)"
    assert hummingbird.publication_type == "Retracted"
    conference = ris_records[_CONFERENCE_EID]
    assert conference.isbn == "979-840072171-7 (ISBN)"
    assert conference.issn is None
    assert conference.conference_name is None


def test_scopus_small_bibtex__keeps_values_as_in_the_file(
    bibtex_records: dict[str, Record],
) -> None:
    hummingbird = bibtex_records[_HUMMINGBIRD_EID]
    assert hummingbird.pmid == "32161388"
    assert hummingbird.publication_type == "Retracted"
    assert (
        bibtex_records[_CONFERENCE_EID]
        .keywords[0]
        .startswith("Author:[ANSYS Simulation; ")
    )


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


# Two big BibTeX entries have a field the BibTeX syntax can't read.
_BIG_MALFORMED_COUNTS = {".bib": 2}


@pytest.mark.big
def test_scopus_big__every_file_parses_with_only_the_known_skips() -> None:
    for path in vendor_files("scopus", "big"):
        suffix = path.suffix.lower()
        if suffix not in _FORMAT_BY_SUFFIX:
            continue
        result = _parse(path, _FORMAT_BY_SUFFIX[suffix])
        assert result.rows, path.name
        assert len(result.skipped) == _BIG_MALFORMED_COUNTS.get(suffix, 0), path.name
        assert all(
            row.reason.startswith("malformed field") for row in result.skipped
        ), path.name
