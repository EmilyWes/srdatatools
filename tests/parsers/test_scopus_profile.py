import csv
from io import StringIO

from app.models.record import Record
from app.parsers.bibtex import parse_bibtex_text, suggest_bibtex_mapping
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import AuthorsRow, FieldMapping, Suggest, make_row
from app.parsers.profiles.scopus import SCOPUS
from app.parsers.ris import parse_ris_text, suggest_ris_mapping
from tests.mappings import mapping_of, targets_of

_CSV_PROFILE = SCOPUS.formats["csv"]
_RIS_PROFILE = SCOPUS.formats["ris"]
_BIBTEX_PROFILE = SCOPUS.formats["bibtex"]


def _suggest_csv(headers: list[str]) -> FieldMapping:
    return suggest_mapping(
        headers,
        _CSV_PROFILE.suggestions,
        _CSV_PROFILE.row_defaults,
        _CSV_PROFILE.ignored_keys,
    )


def _csv_text(row: dict[str, str]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()


def _parse_csv(row: dict[str, str], mapping: FieldMapping | None = None) -> Record:
    mapping = mapping or _suggest_csv(list(row))
    result = parse_csv_text(_csv_text(row), mapping, settings=_CSV_PROFILE.settings)
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


def test_scopus_csv__suggests_author_columns_but_not_abbreviated_names() -> None:
    mapping = _suggest_csv(list(_AUTHOR_ROW))

    assert mapping.rows == {
        "Author full names": AuthorsRow(delimiter=";", id_key="author_full_names"),
        "Author(s) ID": AuthorsRow(
            role="ids", delimiter=";", id_key="scopus_author_id"
        ),
        "Authors with affiliations": AuthorsRow(
            role="affiliations", delimiter=";", id_key="authors_with_affiliations"
        ),
    }


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

    assert targets_of(mapping) == {
        "Conference name": "conference_name",
        "Document Type": "publication_type",
    }


_IDS = "scopus_author_id:60652739200|scopus_author_id:59534195400"


def test_scopus_csv__abbreviated_names_mapped_by_hand() -> None:
    row = {"Authors": "Teng Y.; Han Y.", "Author(s) ID": "60652739200; 59534195400"}

    record = _parse_csv(row, _with_abbreviated_names(_suggest_csv(list(row))))

    assert (record.author_names, record.author_ids) == ("Teng Y.; Han Y.", _IDS)


def _without(mapping: FieldMapping, *ignored: str) -> FieldMapping:
    return FieldMapping(
        rows={k: row for k, row in mapping.rows.items() if k not in ignored}
    )


def _with_abbreviated_names(mapping: FieldMapping) -> FieldMapping:
    row = make_row(Suggest("authors"), "Authors", _CSV_PROFILE.row_defaults)
    return FieldMapping(rows={"Authors": row, **mapping.rows})


def test_scopus_csv__ignored_author_id_column_is_not_used() -> None:
    row = {
        "Authors": "Teng Y.; Han Y.",
        "Author(s) ID": "60652739200; 59534195400",
    }
    mapping = _without(_with_abbreviated_names(_suggest_csv(list(row))), "Author(s) ID")

    record = _parse_csv(row, mapping)

    assert (record.author_names, record.author_ids) == ("Teng Y.; Han Y.", None)


def test_scopus_csv__ignored_full_names_still_give_ids() -> None:
    mapping = _without(_suggest_csv(list(_AUTHOR_ROW)), "Author full names")

    record = _parse_csv(_AUTHOR_ROW, mapping)

    assert (record.author_names, record.author_ids) == (None, _IDS)


def test_scopus_csv__ignored_index_keywords_column_is_not_used() -> None:
    row = {"Author Keywords": "Asia", "Index Keywords": "Thermal"}
    mapping = _without(_suggest_csv(list(row)), "Index Keywords")

    record = _parse_csv(row, mapping)

    assert record.keywords == ["[Author] Asia"]


def test_scopus_csv__unmapped_authors_stay_empty() -> None:
    record = _parse_csv(_AUTHOR_ROW, FieldMapping())

    assert (record.author_names, record.author_ids) == (None, None)


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

    record = _parse_csv(row, FieldMapping())

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
    mapping = suggest_ris_mapping(
        tags, _RIS_PROFILE.suggestions, _RIS_PROFILE.row_defaults
    )
    result = parse_ris_text(text, mapping, settings=_RIS_PROFILE.settings)
    return result.rows[0].record


def test_scopus_ris__publication_type_from_m3_not_ty() -> None:
    mapping = suggest_ris_mapping(["TY", "M3"], _RIS_PROFILE.suggestions)

    assert targets_of(mapping) == {"M3": "publication_type"}


def test_scopus_ris__document_type_and_pmid() -> None:
    record = _parse_ris("M3  - Retracted\nC2  - 32161388\n")

    assert record.publication_type == "Retracted"
    assert record.pmid == "32161388"


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
        mapping = suggest_bibtex_mapping(
            keys, _BIBTEX_PROFILE.suggestions, _BIBTEX_PROFILE.row_defaults
        )
    result = parse_bibtex_text(text, mapping, settings=_BIBTEX_PROFILE.settings)
    return result.rows[0].record


def test_scopus_bibtex__suggests_scopus_fields() -> None:
    keys = ["@type", "type", "pmid", "author_keywords", "keywords"]

    mapping = suggest_bibtex_mapping(keys, _BIBTEX_PROFILE.suggestions)

    assert targets_of(mapping) == {
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


def test_scopus_bibtex__ignored_author_keywords_field_is_not_used() -> None:
    record = _parse_bibtex(
        "author_keywords = {Asia},\nkeywords = {Thermal},\n",
        mapping_of({"keywords": "keywords"}),
    )

    assert record.keywords == ["Thermal"]


def test_scopus_bibtex__unmapped_keywords_stay_empty() -> None:
    record = _parse_bibtex(
        "author_keywords = {Asia},\nkeywords = {Thermal},\n", FieldMapping()
    )

    assert record.keywords == []


def test_scopus_bibtex__non_scopus_url_gives_no_eid() -> None:
    record = _parse_bibtex("url = {https://example.org/publications/123},\n")

    assert record.other_ids == {}


def test_scopus_bibtex__matches_source_field() -> None:
    assert _BIBTEX_PROFILE.matches(
        "@ARTICLE{k,\n\ttitle = {T},\n\tsource = {Scopus},\n}\n"
    )


def test_scopus_bibtex__does_not_match_without_source_field() -> None:
    assert not _BIBTEX_PROFILE.matches("@ARTICLE{k,\n\ttitle = {Scopus}\n}\n")
