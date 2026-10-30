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
        return apply_profile(
            parse_nbib_file(path, mapping, settings=profile.settings), profile, mapping
        )
    headers = list(read_csv_headers(path).samples)
    mapping = suggest_mapping(headers, profile.aliases)
    if profile.list_delimiter is not None:
        mapping = replace(mapping, list_delimiter=profile.list_delimiter)
    return apply_profile(
        parse_csv_file(path, mapping, settings=profile.settings), profile, mapping
    )


def _records_by_pmid(suffix: str, file_format: str) -> dict[str, Record]:
    result = _parse(vendor_file("pubmed", "small", suffix), file_format)
    assert result.skipped == []
    return {row.record.pmid: row.record for row in result.rows if row.record.pmid}


@pytest.fixture
def nbib_records() -> dict[str, Record]:
    return _records_by_pmid(".txt", "nbib")


@pytest.fixture
def csv_records() -> dict[str, Record]:
    return _records_by_pmid(".csv", "csv")


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


def test_pubmed_small_nbib__mesh_keywords_are_prefixed(
    nbib_records: dict[str, Record],
) -> None:
    keywords = nbib_records["41672119"].keywords

    assert "[MeSH] *Materia Medica/standards/history" in keywords
    assert "Adulteration" in keywords


def test_pubmed_small_nbib__book_chapter_uses_book_title_as_journal(
    nbib_records: dict[str, Record],
) -> None:
    record = nbib_records["28590685"]

    assert record.journal == "Micro-, Meso- and Macro-Dynamics of the Brain"
    assert len(record.authors) == 11
    laurent = record.authors[0]
    assert laurent.family_name == "Laurent"
    assert len(laurent.affiliations) == 1
    assert laurent.affiliations[0].name is not None
    assert laurent.affiliations[0].name.startswith(
        "Max Planck Institute for Brain Research"
    )


def test_pubmed_small_nbib__authors_have_orcids_and_affiliations(
    nbib_records: dict[str, Record],
) -> None:
    authors = nbib_records["37587301"].authors

    assert len(authors) == 9
    muller, garcia, nesbitt = authors[0], authors[2], authors[8]
    assert (muller.family_name, muller.given_name) == ("Müller", "Rodrigo T")
    assert muller.orcid == "0000-0001-8894-9875"
    assert len(muller.affiliations) == 2
    assert muller.affiliations[1].name == (
        "Programa de Pós-Graduação em Biodiversidade Animal, Universidade Federal "
        "de Santa Maria, Santa Maria, Brazil. rodrigotmuller@hotmail.com."
    )
    assert garcia.orcid is None
    assert len(garcia.affiliations) == 2
    assert nesbitt.orcid == "0000-0002-7017-1652"
    assert [a.name for a in nesbitt.affiliations] == [
        "Department of Geosciences, Virginia Tech, Blacksburg, VA, USA."
    ]


def test_pubmed_small_csv__parses_every_record(
    csv_records: dict[str, Record],
) -> None:
    assert len(csv_records) == 12


def test_pubmed_small_csv__applies_profile_fixes(
    csv_records: dict[str, Record],
) -> None:
    nature = csv_records["37587301"]
    assert nature.volume is None
    assert nature.publication_date == PartialDate(year=2023)
    assert csv_records["30527956"].authors[-1].full_name == "Walsworth AK"
    assert csv_records["37886492"].other_ids["pmc"] == "PMC10602114"


def test_pubmed_small__nbib_and_csv_agree_on_ids(
    nbib_records: dict[str, Record], csv_records: dict[str, Record]
) -> None:
    assert nbib_records.keys() == csv_records.keys()
    for pmid, record in nbib_records.items():
        assert record.doi == csv_records[pmid].doi, pmid


@pytest.mark.big
def test_pubmed_big__every_file_parses_without_skips() -> None:
    for path in vendor_files("pubmed", "big"):
        result = _parse(path, _FORMAT_BY_SUFFIX[path.suffix.lower()])
        assert result.rows, path.name
        assert result.skipped == [], path.name
