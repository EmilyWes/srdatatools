from dataclasses import replace
from pathlib import Path

import pytest

from app.models.record import PartialDate, Record
from app.parsers.common import ParseResult
from app.parsers.csv_ import parse_csv_file, read_csv_headers, suggest_mapping
from app.parsers.nbib import parse_nbib_file, read_nbib_tags, suggest_nbib_mapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.pubmed import PUBMED
from tests.vendor_data import vendor_file, vendor_files

_FORMAT_BY_SUFFIX = {".txt": "nbib", ".nbib": "nbib", ".csv": "csv"}


def _parse(path: Path, file_format: str) -> ParseResult:
    profile = PUBMED.formats[file_format]
    if file_format == "nbib":
        tags = list(read_nbib_tags(path).samples)
        mapping = suggest_nbib_mapping(tags, profile.aliases)
        return apply_profile(parse_nbib_file(path, mapping), profile)
    headers = list(read_csv_headers(path).samples)
    mapping = suggest_mapping(headers, profile.aliases)
    if profile.list_delimiter is not None:
        mapping = replace(mapping, list_delimiter=profile.list_delimiter)
    return apply_profile(parse_csv_file(path, mapping), profile)


def _records_by_pmid(name: str, file_format: str) -> dict[str, Record]:
    result = _parse(vendor_file("small", "pubmed", name), file_format)
    assert result.skipped == []
    return {row.record.pmid: row.record for row in result.rows if row.record.pmid}


@pytest.fixture
def nbib_records() -> dict[str, Record]:
    return _records_by_pmid("small_261016.txt", "nbib")


@pytest.fixture
def csv_records() -> dict[str, Record]:
    return _records_by_pmid("small_261016.csv", "csv")


def test_pubmed_small_nbib__parses_every_record(
    nbib_records: dict[str, Record],
) -> None:
    assert len(nbib_records) == 12


def test_pubmed_small_nbib__applies_profile_fixes(
    nbib_records: dict[str, Record],
) -> None:
    assert nbib_records["41672119"].journal == "Journal of ethnopharmacology"
    assert nbib_records["27869079"].title == (
        "Clin d’œil du Dinosaure émérite - Quand les parents DMD montent au "
        "créneau de la FDA…."
    )
    assert nbib_records["11523304"].pages == "521-522"
    assert nbib_records["11523304"].doi is None
    assert nbib_records["28590685"].isbn == "978-3-319-28801-7"
    assert nbib_records["28590685"].publication_type == "Review"


def test_pubmed_small_csv__parses_every_record(
    csv_records: dict[str, Record],
) -> None:
    assert len(csv_records) == 12


def test_pubmed_small_csv__applies_profile_fixes(
    csv_records: dict[str, Record],
) -> None:
    nature = csv_records["37587301"]
    assert (nature.volume, nature.issue, nature.pages) == ("620", "7974", "589-594")
    assert nature.publication_date == PartialDate(year=2023, month=8)
    assert csv_records["11523304"].pages == "521-522"
    assert csv_records["30527956"].authors[-1].full_name == "Walsworth AK"
    assert csv_records["28590685"].volume is None
    assert csv_records["37886492"].other_ids["pmc"] == "PMC10602114"


def test_pubmed_small__nbib_and_csv_agree_on_ids(
    nbib_records: dict[str, Record], csv_records: dict[str, Record]
) -> None:
    assert nbib_records.keys() == csv_records.keys()
    for pmid, record in nbib_records.items():
        assert record.doi == csv_records[pmid].doi, pmid


@pytest.mark.big
def test_pubmed_big__every_file_parses_without_skips() -> None:
    for path in vendor_files("big", "pubmed"):
        result = _parse(path, _FORMAT_BY_SUFFIX[path.suffix.lower()])
        assert result.rows, path.name
        assert result.skipped == [], path.name
