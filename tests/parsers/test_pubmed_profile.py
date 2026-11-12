import csv
from io import StringIO

from app.models.record import Record
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import AuthorsRow, FieldMapping, OtherIdRow, ScalarRow
from app.parsers.nbib import parse_nbib_text, suggest_nbib_mapping
from app.parsers.profiles.pubmed import PUBMED
from tests.mappings import targets_of


def _parse_nbib(text: str) -> Record:
    tags = list(dict.fromkeys(line[:4].strip() for line in text.splitlines()))
    profile = PUBMED.formats["nbib"]
    mapping = suggest_nbib_mapping(tags, profile.suggestions, profile.row_defaults)
    result = parse_nbib_text(text, mapping, settings=profile.settings)
    return result.rows[0].record


def _suggest_csv(headers: list[str]) -> FieldMapping:
    profile = PUBMED.formats["csv"]
    return suggest_mapping(headers, profile.suggestions, profile.row_defaults)


def _parse_csv(row: dict[str, str]) -> Record:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    profile = PUBMED.formats["csv"]
    mapping = _suggest_csv(list(row))
    result = parse_csv_text(out.getvalue(), mapping, settings=profile.settings)
    return result.rows[0].record


def test_pubmed_nbib__journal_uses_jt_not_ta() -> None:
    record = _parse_nbib("PMID- 1\nTA  - Nature\nJT  - Nature reviews\n")

    assert record.journal == "Nature reviews"


def test_pubmed_nbib__book_title_fills_journal() -> None:
    record = _parse_nbib("PMID- 1\nBTI - Micro-, Meso- and Macro-Dynamics\n")

    assert record.journal == "Micro-, Meso- and Macro-Dynamics"


def test_pubmed_nbib__suggests_tt_as_title() -> None:
    mapping = suggest_nbib_mapping(["TI", "TT"], PUBMED.formats["nbib"].suggestions)

    assert targets_of(mapping) == {"TI": "title", "TT": "title"}


def test_pubmed_nbib__bracketed_translated_title_is_kept() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - [Introduction to paleopathology].\nTT  - Introduction.\n"
    )

    assert record.title == "[Introduction to paleopathology]."


def test_pubmed_nbib__leaves_ordinary_record_unchanged() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - Some Paper.\nPG  - 589-594\nPT  - Letter\n"
        "ISBN- 978-3-319-28801-7\n"
    )

    assert record.title == "Some Paper."
    assert record.pages == "589-594"
    assert record.publication_type == "Letter"
    assert record.isbn == "978-3-319-28801-7"


def test_pubmed_csv__suggests_exact_journal_and_nbib_id_keys() -> None:
    mapping = _suggest_csv(["Journal/Book", "PMCID", "NIHMS ID"])

    assert mapping.rows == {
        "Journal/Book": ScalarRow(target="journal"),
        "PMCID": OtherIdRow(key="pmc"),
        "NIHMS ID": OtherIdRow(key="mid"),
    }
    assert mapping.match_kinds["Journal/Book"] == "exact"


def test_pubmed_csv__suggests_author_names_split_on_comma() -> None:
    assert _suggest_csv(["Authors"]).rows == {
        "Authors": AuthorsRow(role="names", delimiter=",", id_key="authors")
    }


def test_pubmed_nbib__matches_nlm_owned_records() -> None:
    assert PUBMED.formats["nbib"].matches("PMID- 1\nOWN - NLM\nTI  - Title\n")


def test_pubmed_nbib__does_not_match_without_own_nlm() -> None:
    assert not PUBMED.formats["nbib"].matches("PMID- 1\nOWN - OTHER\nTI  - Title\n")


def test_pubmed_csv__matches_pubmed_headers() -> None:
    text = "PMID,Title,Citation,Journal/Book,DOI\n1,A,B,C,D\n"

    assert PUBMED.formats["csv"].matches(text)


def test_pubmed_csv__does_not_match_generic_headers() -> None:
    assert not PUBMED.formats["csv"].matches("PMID,Title,DOI\n1,A,D\n")
