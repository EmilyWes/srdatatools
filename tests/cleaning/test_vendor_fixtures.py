from pathlib import Path

from app.cleaning.options import CleaningOptions
from app.cleaning.steps import CleaningContext, clean_record, file_separators
from app.models.record import Record
from app.parsers.authors import AUTHOR_JOINER, parse_author_ids
from app.parsers.bibtex import (
    parse_bibtex_file,
    read_bibtex_fields,
    suggest_bibtex_mapping,
)
from app.parsers.common import FileType
from app.parsers.csv_ import parse_csv_file, read_csv_headers, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.nbib import parse_nbib_file, read_nbib_tags, suggest_nbib_mapping
from app.parsers.profiles import profile_for
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping
from tests.vendor_data import vendor_file

_OPTIONS = CleaningOptions()


def _mapping(path: Path, file_type: FileType, source: str) -> FieldMapping:
    profile = profile_for(source, file_type)
    assert profile is not None
    if file_type == "csv":
        headers = list(read_csv_headers(path).samples)
        return suggest_mapping(headers, profile.suggestions, profile.ignored_keys)
    if file_type == "ris":
        tags = list(read_ris_tags(path).samples)
        return suggest_ris_mapping(tags, profile.suggestions, profile.ignored_keys)
    if file_type == "nbib":
        tags = list(read_nbib_tags(path).samples)
        return suggest_nbib_mapping(tags, profile.suggestions, profile.ignored_keys)
    keys = list(read_bibtex_fields(path).samples)
    return suggest_bibtex_mapping(keys, profile.suggestions, profile.ignored_keys)


def _cleaned(
    vendor: str, suffix: str, file_type: FileType, options: CleaningOptions = _OPTIONS
) -> list[Record]:
    """Parsed with the vendor's profile, then cleaned as one source file."""
    path = vendor_file(vendor, "small", suffix)
    mapping = _mapping(path, file_type, vendor)
    profile = profile_for(vendor, file_type)
    assert profile is not None
    settings = profile.settings
    if file_type == "csv":
        result = parse_csv_file(path, mapping, settings=settings)
    elif file_type == "ris":
        result = parse_ris_file(path, mapping, settings)
    elif file_type == "nbib":
        result = parse_nbib_file(path, mapping, settings)
    else:
        result = parse_bibtex_file(path, mapping, settings)
    records = [row.record for row in result.rows]
    names, affiliations, ids, keywords = file_separators(records, options)
    return [
        clean_record(
            row.record,
            CleaningContext(
                raw_fields=row.raw_fields,
                mapping=mapping,
                names_separator=names,
                affiliations_separator=affiliations,
                ids_separator=ids,
                keywords_separator=keywords,
            ),
            options,
        )[0]
        for row in result.rows
    ]


def _by(records: list[Record], key: str) -> dict[str, Record]:
    return {
        record.other_ids[key] if key == "eid" else getattr(record, key): record
        for record in records
    }


def test_cleaned_scopus_csv__splits_authors_and_moves_ids_out_of_names() -> None:
    options = _OPTIONS.model_copy(update={"affiliation_start": ", "})
    record = _by(_cleaned("scopus", ".csv", "csv", options), "eid")[
        "2-s2.0-105050698470"
    ]
    names = (record.author_names or "").split(AUTHOR_JOINER)
    ids = parse_author_ids(record.author_ids)

    assert names[0] == "Oyabu, Shumpei"
    assert len(names) == len(ids) == 5
    assert ids[0] == ["scopus_author_id:60900075400"]
    assert (record.author_affiliations or "").startswith(
        "Department of Natural History and Planetary Sciences, Hokkaido University,"
        " Kita 10, Nishi 8, Kita-ku, Hokkaido, Sapporo, 060-0810, Japan|"
    )


def test_cleaned_scopus_csv__splits_keywords_keeping_the_author_prefix() -> None:
    keywords = _by(_cleaned("scopus", ".csv", "csv"), "eid")[
        "2-s2.0-105040180364"
    ].keywords

    assert "[Author] ANSYS Simulation" in keywords
    assert "Balancing" in keywords
    assert not any(":[" in keyword for keyword in keywords)


def test_cleaned_scopus_ris__reads_eid_and_conference_name_from_notes() -> None:
    records = _by(_cleaned("scopus", ".ris", "ris"), "eid")

    hummingbird = records["2-s2.0-85081690252"]
    assert hummingbird.issn == "00280836"
    conference = records["2-s2.0-105040180364"]
    assert conference.isbn == "979-840072171-7"
    assert conference.conference_name == (
        "5th International Conference on Computer, Artificial Intelligence and "
        "Control Engineering, CAICE 2026"
    )


_SCOPUS_FORMATS: tuple[tuple[str, FileType], ...] = (
    (".csv", "csv"),
    (".ris", "ris"),
    (".bib", "bibtex"),
)


def test_cleaned_scopus__every_format_gets_the_same_eids() -> None:
    eids = [
        set(_by(_cleaned("scopus", suffix, file_type), "eid"))
        for suffix, file_type in _SCOPUS_FORMATS
    ]

    assert eids[0] == eids[1] == eids[2]
    assert len(eids[0]) == 10


def test_cleaned_pubmed_nbib__applies_the_defaults() -> None:
    records = _by(_cleaned("pubmed", ".txt", "nbib"), "pmid")

    assert records["27869079"].title == (
        "Clin d’œil du Dinosaure émérite - Quand les parents DMD montent au "
        "créneau de la FDA…."
    )
    assert records["11523304"].pages == "521-522"
    assert records["28590685"].isbn == "978-3-319-28801-7"
    assert records["28590685"].publication_type == "Review"


def test_cleaned_pubmed_csv__fills_parts_from_citation_and_drops_et_al() -> None:
    records = _by(_cleaned("pubmed", ".csv", "csv"), "pmid")

    nature = records["37587301"]
    assert (nature.volume, nature.issue, nature.pages) == ("620", "7974", "589-594")
    assert records["11523304"].pages == "521-522"
    assert (records["30527956"].author_names or "").endswith(", Walsworth AK")


def test_cleaned_openalex_csv__groups_author_ids_and_orcids() -> None:
    records = {r.doi: r for r in _cleaned("openalex", ".csv", "csv")}

    dinosaur = records["10.1038/nature21700"]
    assert set(parse_author_ids(dinosaur.author_ids)[0]) == {
        "orcid:0000-0001-9069-7638",
        "openalex_author_id:A5091833725",
    }

    chicken = records["10.1038/nature03154"]
    names = (chicken.author_names or "").split(AUTHOR_JOINER)
    ids = parse_author_ids(chicken.author_ids)
    assert len(names) == len(ids) == 100
    assert ids[0] == []
    assert names[12] == "John D. McPherson"
    assert set(ids[12]) == {
        "orcid:0000-0001-8049-9347",
        "openalex_author_id:A5047690257",
    }


def test_cleaned_openalex_csv__strips_pmid_and_keeps_one_issn() -> None:
    [dinosaur] = [
        record
        for record in _cleaned("openalex", ".csv", "csv")
        if record.doi == "10.1038/nature21700"
    ]

    assert dinosaur.pmid == "28332513"
    assert dinosaur.issn == "0028-0836"
