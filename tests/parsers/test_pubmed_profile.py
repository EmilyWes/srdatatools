import csv
from io import StringIO

from app.models.record import PartialDate, Record
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import AuthorsRow, FieldMapping, OtherIdRow, ScalarRow
from app.parsers.nbib import parse_nbib_text, suggest_nbib_mapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.pubmed import PUBMED
from tests.mappings import mapping_of, targets_of


def _parse_nbib(text: str) -> Record:
    tags = list(dict.fromkeys(line[:4].strip() for line in text.splitlines()))
    profile = PUBMED.formats["nbib"]
    mapping = suggest_nbib_mapping(tags, profile.suggestions, profile.row_defaults)
    result = apply_profile(
        parse_nbib_text(text, mapping, settings=profile.settings), profile, mapping
    )
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
    result = apply_profile(
        parse_csv_text(out.getvalue(), mapping, settings=profile.settings),
        profile,
        mapping,
    )
    return result.rows[0].record


def test_pubmed_nbib__journal_uses_jt_not_ta() -> None:
    record = _parse_nbib("PMID- 1\nTA  - Nature\nJT  - Nature reviews\n")

    assert record.journal == "Nature reviews"


def test_pubmed_nbib__book_title_fills_journal() -> None:
    record = _parse_nbib("PMID- 1\nBTI - Micro-, Meso- and Macro-Dynamics\n")

    assert record.journal == "Micro-, Meso- and Macro-Dynamics"


def test_pubmed_nbib__not_available_title_uses_tt() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - [Not Available].\nTT  - Clin d'oeil du Dinosaure.\n"
    )

    assert record.title == "Clin d'oeil du Dinosaure."


def test_pubmed_nbib__suggests_tt_as_title() -> None:
    mapping = suggest_nbib_mapping(["TI", "TT"], PUBMED.formats["nbib"].suggestions)

    assert targets_of(mapping) == {"TI": "title", "TT": "title"}


def test_pubmed_nbib__ignored_tt_gives_no_title() -> None:
    text = "PMID- 1\nTI  - [Not Available].\nTT  - Clin d'oeil du Dinosaure.\n"
    profile = PUBMED.formats["nbib"]
    mapping = mapping_of({"TI": "title"})

    record = apply_profile(
        parse_nbib_text(text, mapping, settings=profile.settings), profile, mapping
    )

    assert record.rows[0].record.title is None


def test_pubmed_nbib__not_available_title_without_tt_is_none() -> None:
    record = _parse_nbib("PMID- 1\nTI  - [Not Available].\n")

    assert record.title is None


def test_pubmed_nbib__bracketed_translated_title_is_kept() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - [Introduction to paleopathology].\nTT  - Introduction.\n"
    )

    assert record.title == "[Introduction to paleopathology]."


def test_pubmed_nbib__expands_abbreviated_pages() -> None:
    record = _parse_nbib("PMID- 1\nPG  - 521-2\n")

    assert record.pages == "521-522"


def test_pubmed_nbib__keeps_first_publication_type() -> None:
    record = _parse_nbib(
        "PMID- 1\nPT  - Journal Article\nPT  - Retracted Publication\n"
    )

    assert record.publication_type == "Journal Article"


def test_pubmed_nbib__keeps_first_isbn() -> None:
    record = _parse_nbib("PMID- 1\nISBN- 978-3-319-28801-7\nISBN- 978-3-319-28802-4\n")

    assert record.isbn == "978-3-319-28801-7"


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


def test_pubmed_csv__strips_trailing_period_from_last_author() -> None:
    record = _parse_csv({"PMID": "1", "Authors": "Romano M, Novacek MJ."})

    assert record.author_names == "Romano M, Novacek MJ"


def test_pubmed_csv__drops_et_al() -> None:
    record = _parse_csv({"PMID": "1", "Authors": "Rhodes CJ, Walsworth AK, et al."})

    assert record.author_names == "Rhodes CJ, Walsworth AK"


def test_pubmed_csv__fills_volume_issue_and_pages_from_citation() -> None:
    record = _parse_csv(
        {
            "PMID": "1",
            "Citation": "Nature. 2023 Aug;620(7974):589-594. doi: x.",
            "Publication Year": "2023",
        }
    )

    assert (record.volume, record.issue, record.pages) == ("620", "7974", "589-594")
    assert record.publication_date == PartialDate(year=2023)


def test_pubmed_csv__expands_short_page_range_from_citation() -> None:
    record = _parse_csv({"PMID": "1", "Citation": "Rev Med Liege. 2001;56(7):521-2."})

    assert record.pages == "521-522"


def test_pubmed_nbib__matches_nlm_owned_records() -> None:
    assert PUBMED.formats["nbib"].matches("PMID- 1\nOWN - NLM\nTI  - Title\n")


def test_pubmed_nbib__does_not_match_without_own_nlm() -> None:
    assert not PUBMED.formats["nbib"].matches("PMID- 1\nOWN - OTHER\nTI  - Title\n")


def test_pubmed_csv__matches_pubmed_headers() -> None:
    text = "PMID,Title,Citation,Journal/Book,DOI\n1,A,B,C,D\n"

    assert PUBMED.formats["csv"].matches(text)


def test_pubmed_csv__does_not_match_generic_headers() -> None:
    assert not PUBMED.formats["csv"].matches("PMID,Title,DOI\n1,A,D\n")
