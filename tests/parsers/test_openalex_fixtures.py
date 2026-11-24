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
from app.parsers.detect import detect_sources
from app.parsers.mapping import FieldMapping
from app.parsers.profiles.openalex import OPENALEX
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping
from tests.vendor_data import vendor_file, vendor_files

_FORMAT_BY_SUFFIX: dict[str, FileType] = {
    ".csv": "csv",
    ".ris": "ris",
    ".bib": "bibtex",
}

_CHICKEN_DOI = "10.1038/nature03154"
_DINOSAUR_DOI = "10.1038/nature21700"


def _parse(path: Path, file_format: FileType) -> ParseResult:
    profile = OPENALEX.formats[file_format]
    mapping: FieldMapping
    if file_format == "csv":
        headers = list(read_csv_headers(path).samples)
        mapping = suggest_mapping(headers, profile.suggestions, profile.ignored_keys)
    elif file_format == "ris":
        mapping = suggest_ris_mapping(
            list(read_ris_tags(path).samples), profile.suggestions, profile.ignored_keys
        )
    else:
        keys = list(read_bibtex_fields(path).samples)
        mapping = suggest_bibtex_mapping(
            keys, profile.suggestions, profile.ignored_keys
        )
    if file_format == "csv":
        result = parse_csv_file(path, mapping, settings=profile.settings)
    elif file_format == "ris":
        result = parse_ris_file(path, mapping, profile.settings)
    else:
        result = parse_bibtex_file(path, mapping, profile.settings)
    return result


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

    assert detect_sources(path, "csv") == ("openalex",)


@pytest.mark.parametrize("suffix", [".ris", ".bib"])
def test_openalex_small__ris_and_bibtex_are_not_detected(suffix: str) -> None:
    path = vendor_file("openalex", "small", suffix)

    assert detect_sources(path, _FORMAT_BY_SUFFIX[suffix]) == ()


def test_openalex_small_csv__keeps_author_id_columns_unsplit(
    csv_records: dict[str, Record],
) -> None:
    dinosaur = csv_records[_DINOSAUR_DOI]

    [names] = dinosaur.author_names
    assert names.startswith("Matthew G. Baron|")
    assert list(dinosaur.author_ids) == ["openalex_author_id", "orcid"]
    assert dinosaur.author_ids["openalex_author_id"][0].startswith("A5091833725|")
    assert dinosaur.author_ids["orcid"][0].startswith(
        "https://orcid.org/0000-0001-9069-7638|"
    )


def test_openalex_small_csv__keeps_values_as_in_the_file(
    csv_records: dict[str, Record],
) -> None:
    dinosaur = csv_records[_DINOSAUR_DOI]
    assert dinosaur.pmid == "https://pubmed.ncbi.nlm.nih.gov/28332513"
    assert dinosaur.issn == ["0028-0836|1476-4687"]
    assert dinosaur.journal == "Nature"
    assert dinosaur.publication_type == "article"
    assert dinosaur.other_ids == {"openalex": "W2601753892"}
    keywords = dinosaur.keywords
    assert keywords[""][0].startswith("dinosaur phylogeny|")
    assert keywords["Concept"][0].startswith("Theropoda|")
    assert keywords["Topic"] == ["Paleontology and Evolutionary Biology"]


def test_openalex_small_ris__joins_au_and_c1_lines(
    ris_records: dict[str, Record],
) -> None:
    dinosaur = ris_records[_DINOSAUR_DOI]

    assert dinosaur.author_names[:2] == ["Baron, Matthew", "NORMAN, DAVID"]
    assert dinosaur.author_affiliations[0] == (
        "Department of Earth Sciences, Natural History Museum, Cromwell Road, "
        "London SW7 5BD, UK"
    )
    assert ris_records[_CHICKEN_DOI].author_affiliations


def test_openalex_small_bibtex__keeps_keywords_unsplit(
    bibtex_records: dict[str, Record],
) -> None:
    [keywords] = bibtex_records[_DINOSAUR_DOI].keywords[""]
    assert keywords.startswith("dinosaur phylogeny, Ornithischia, ")


def test_openalex_small__formats_agree_on_ids_and_titles(
    csv_records: dict[str, Record],
    ris_records: dict[str, Record],
    bibtex_records: dict[str, Record],
) -> None:
    assert csv_records.keys() == ris_records.keys() == bibtex_records.keys()
    for doi, record in csv_records.items():
        for other in (ris_records[doi], bibtex_records[doi]):
            assert other.title == record.title, doi
            names = record.author_names[0].split("|") if record.author_names else []
            assert len(other.author_names) == len(names), doi


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
