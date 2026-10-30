from dataclasses import replace
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
from app.parsers.mapping import FieldMapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.openalex import OPENALEX
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping
from tests.vendor_data import vendor_file, vendor_files

_FORMAT_BY_SUFFIX = {".csv": "csv", ".ris": "ris", ".bib": "bibtex"}

_CHICKEN_DOI = "10.1038/nature03154"
_DINOSAUR_DOI = "10.1038/nature21700"


def _parse(path: Path, file_format: str) -> ParseResult:
    profile = OPENALEX.formats[file_format]
    mapping: FieldMapping
    if file_format == "csv":
        headers = list(read_csv_headers(path).samples)
        mapping = suggest_mapping(headers, profile.aliases, profile.ignored_keys)
    elif file_format == "ris":
        mapping = suggest_ris_mapping(
            list(read_ris_tags(path).samples), profile.aliases
        )
    else:
        keys = list(read_bibtex_fields(path).samples)
        mapping = suggest_bibtex_mapping(keys, profile.aliases)
    if profile.list_delimiter is not None:
        mapping = replace(mapping, list_delimiter=profile.list_delimiter)
    parse = {"csv": parse_csv_file, "ris": parse_ris_file}.get(
        file_format, parse_bibtex_file
    )
    return apply_profile(parse(path, mapping), profile)


def _records_by_doi(suffix: str) -> dict[str, Record]:
    result = _parse(vendor_file("openalex", "small", suffix), _FORMAT_BY_SUFFIX[suffix])
    assert result.skipped == []
    assert len(result.rows) == 12
    return {row.record.doi: row.record for row in result.rows if row.record.doi}


@pytest.fixture
def csv_records() -> dict[str, Record]:
    return _records_by_doi(".csv")


@pytest.fixture
def ris_records() -> dict[str, Record]:
    return _records_by_doi(".ris")


@pytest.fixture
def bibtex_records() -> dict[str, Record]:
    return _records_by_doi(".bib")


def test_openalex_small_csv__detects_openalex_source() -> None:
    path = vendor_file("openalex", "small", ".csv")

    assert detect_source(path, "csv") == "openalex"


@pytest.mark.parametrize("suffix", [".ris", ".bib"])
def test_openalex_small__ris_and_bibtex_are_not_detected(suffix: str) -> None:
    path = vendor_file("openalex", "small", suffix)

    assert detect_source(path, _FORMAT_BY_SUFFIX[suffix]) is None


def test_openalex_small_csv__zips_author_ids_and_orcids(
    csv_records: dict[str, Record],
) -> None:
    baron = csv_records[_DINOSAUR_DOI].authors[0]
    assert baron.full_name == "Matthew G. Baron"
    assert baron.orcid == "0000-0001-9069-7638"
    assert baron.other_ids == {"openalex_author_id": "A5091833725"}

    chicken_authors = csv_records[_CHICKEN_DOI].authors
    assert len(chicken_authors) == 100
    hillier = chicken_authors[0]
    assert (hillier.orcid, hillier.other_ids) == (None, {})
    mcpherson = chicken_authors[12]
    assert mcpherson.full_name == "John D. McPherson"
    assert mcpherson.orcid == "0000-0001-8049-9347"
    assert mcpherson.other_ids == {"openalex_author_id": "A5047690257"}


def test_openalex_small_csv__applies_profile_fixes(
    csv_records: dict[str, Record],
) -> None:
    dinosaur = csv_records[_DINOSAUR_DOI]
    assert dinosaur.pmid == "28332513"
    assert dinosaur.issn == "0028-0836"
    assert dinosaur.journal == "Nature"
    assert dinosaur.publication_type == "article"
    assert dinosaur.other_ids == {"openalex": "W2601753892"}
    assert "dinosaur phylogeny" in dinosaur.keywords
    assert "[Concept] Theropoda" in dinosaur.keywords
    assert "[Topic] Paleontology and Evolutionary Biology" in dinosaur.keywords


def test_openalex_small_ris__attaches_c1_affiliations_to_authors(
    ris_records: dict[str, Record],
) -> None:
    baron, norman, _ = ris_records[_DINOSAUR_DOI].authors

    assert baron.full_name == "Baron, Matthew"
    assert baron.affiliations[0].name == (
        "Department of Earth Sciences, Natural History Museum, Cromwell Road, "
        "London SW7 5BD, UK"
    )
    assert norman.full_name == "NORMAN, DAVID"
    assert norman.affiliations
    assert ris_records[_CHICKEN_DOI].authors[0].affiliations


def test_openalex_small_bibtex__splits_keywords_on_comma(
    bibtex_records: dict[str, Record],
) -> None:
    assert bibtex_records[_DINOSAUR_DOI].keywords[:2] == [
        "dinosaur phylogeny",
        "Ornithischia",
    ]


def test_openalex_small__formats_agree_on_ids_and_titles(
    csv_records: dict[str, Record],
    ris_records: dict[str, Record],
    bibtex_records: dict[str, Record],
) -> None:
    assert csv_records.keys() == ris_records.keys() == bibtex_records.keys()
    for doi, record in csv_records.items():
        for other in (ris_records[doi], bibtex_records[doi]):
            assert other.title == record.title, doi
            assert len(other.authors) == len(record.authors), doi


@pytest.mark.big
def test_openalex_big__every_file_parses_without_unexpected_skips() -> None:
    for path in vendor_files("openalex", "big"):
        file_format = _FORMAT_BY_SUFFIX.get(path.suffix.lower())
        if file_format is None:
            continue
        result = _parse(path, file_format)
        assert result.rows, path.name
        if file_format == "bibtex":
            # OpenAlex escapes "{" as "\{" in some abstracts but not the matching "}".
            reasons = {skip.reason for skip in result.skipped}
            assert reasons <= {"entry has unbalanced braces"}, path.name
        else:
            assert result.skipped == [], path.name
