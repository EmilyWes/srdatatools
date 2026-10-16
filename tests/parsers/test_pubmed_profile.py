import csv
from dataclasses import replace
from io import StringIO

import pytest

from app.models.record import PartialDate, Record
from app.parsers.csv_ import parse_csv_text, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.nbib import parse_nbib_text, suggest_nbib_mapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.pubmed import PUBMED, expand_page_range


def _parse_nbib(text: str) -> Record:
    tags = list(dict.fromkeys(line[:4].strip() for line in text.splitlines()))
    profile = PUBMED.formats["nbib"]
    mapping = suggest_nbib_mapping(tags, profile.aliases)
    result = apply_profile(parse_nbib_text(text, mapping), profile)
    return result.rows[0].record


def _suggest_csv(headers: list[str]) -> FieldMapping:
    profile = PUBMED.formats["csv"]
    assert profile.list_delimiter is not None
    mapping = suggest_mapping(headers, profile.aliases)
    return replace(mapping, list_delimiter=profile.list_delimiter)


def _parse_csv(row: dict[str, str]) -> Record:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    profile = PUBMED.formats["csv"]
    mapping = _suggest_csv(list(row))
    result = apply_profile(parse_csv_text(out.getvalue(), mapping), profile)
    return result.rows[0].record


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        ("521-2", "521-522"),
        ("3705-6", "3705-3706"),
        ("1199-201", "1199-1201"),
        ("1-2", "1-2"),
        ("589-594", "589-594"),
        ("121354", "121354"),
        ("e123", "e123"),
        ("S12-5", "S12-5"),
    ],
)
def test_expand_page_range__expands_only_abbreviated_numeric_ranges(
    pages: str, expected: str
) -> None:
    assert expand_page_range(pages) == expected


def test_pubmed_nbib__journal_uses_jt_not_ta() -> None:
    record = _parse_nbib("PMID- 1\nTA  - Nature\nJT  - Nature reviews\n")

    assert record.journal == "Nature reviews"


def test_pubmed_nbib__not_available_title_uses_tt() -> None:
    record = _parse_nbib(
        "PMID- 1\nTI  - [Not Available].\nTT  - Clin d'oeil du Dinosaure.\n"
    )

    assert record.title == "Clin d'oeil du Dinosaure."


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

    assert mapping.targets == {
        "Journal/Book": "journal",
        "PMCID": "other_ids.pmc",
        "NIHMS ID": "other_ids.mid",
    }
    assert mapping.match_kinds["Journal/Book"] == "exact"


def test_pubmed_csv__suggests_comma_list_delimiter() -> None:
    assert _suggest_csv(["Authors"]).list_delimiter == ","


def test_pubmed_csv__strips_trailing_period_from_last_author() -> None:
    record = _parse_csv({"PMID": "1", "Authors": "Romano M, Novacek MJ."})

    assert [a.full_name for a in record.authors] == ["Romano M", "Novacek MJ"]


def test_pubmed_csv__drops_et_al() -> None:
    record = _parse_csv({"PMID": "1", "Authors": "Rhodes CJ, Walsworth AK, et al."})

    assert [a.full_name for a in record.authors] == ["Rhodes CJ", "Walsworth AK"]


def test_pubmed_csv__citation_fills_volume_issue_pages_and_month() -> None:
    record = _parse_csv(
        {
            "PMID": "1",
            "Citation": "Nature. 2023 Aug;620(7974):589-594. doi: x. Epub 2023.",
            "Publication Year": "2023",
        }
    )

    assert record.volume == "620"
    assert record.issue == "7974"
    assert record.pages == "589-594"
    assert record.publication_date == PartialDate(year=2023, month=8)


def test_pubmed_csv__citation_without_issue_fills_day() -> None:
    record = _parse_csv(
        {
            "PMID": "1",
            "Citation": "J Ethnopharmacol. 2026 May 10;362:121354. doi: 10.1016/x.",
            "Publication Year": "2026",
        }
    )

    assert record.volume == "362"
    assert record.issue is None
    assert record.pages == "121354"
    assert record.publication_date == PartialDate(year=2026, month=5, day=10)


def test_pubmed_csv__citation_pages_are_expanded() -> None:
    record = _parse_csv(
        {"PMID": "1", "Citation": "Rev Med Liege. 2001 Jul;56(7):521-2."}
    )

    assert record.pages == "521-522"


def test_pubmed_csv__citation_keeps_page_suffix() -> None:
    record = _parse_csv(
        {"PMID": "1", "Citation": "Curr Biol. 2021 Aug 23;31(16):3687-3693.e5. doi: x."}
    )

    assert record.pages == "3687-3693.e5"


def test_pubmed_csv__citation_volume_may_contain_text() -> None:
    record = _parse_csv(
        {
            "PMID": "1",
            "Citation": "Med Sci (Paris). 2016 Nov;32 Hors série n°2:57-59. doi: x.",
        }
    )

    assert record.volume == "32 Hors série n°2"
    assert record.pages == "57-59"


def test_pubmed_csv__citation_without_year_column_sets_full_date() -> None:
    record = _parse_csv(
        {"PMID": "1", "Citation": "Nature. 2023 Aug;620(7974):589-594."}
    )

    assert record.publication_date == PartialDate(year=2023, month=8)


def test_pubmed_csv__citation_date_of_other_year_is_ignored() -> None:
    record = _parse_csv(
        {
            "PMID": "1",
            "Citation": "Nature. 2023 Aug;620(7974):589-594.",
            "Publication Year": "2024",
        }
    )

    assert record.publication_date == PartialDate(year=2024)


def test_pubmed_csv__citation_does_not_overwrite_mapped_fields() -> None:
    record = _parse_csv(
        {
            "PMID": "1",
            "Citation": "Nature. 2023 Aug;620(7974):589-594.",
            "Volume": "99",
        }
    )

    assert record.volume == "99"
    assert record.issue == "7974"


@pytest.mark.parametrize(
    "citation",
    [
        "2016 May 3. In: Buzsáki G, Christen Y, editors. Micro-, Meso- and "
        "Macro-Dynamics of the Brain [Internet]. Cham (CH): Springer; 2016.",
        "Res Sq [Preprint]. 2023 Oct 3:rs.3.rs-3382427. doi: 10.21203/x.",
    ],
)
def test_pubmed_csv__non_journal_citation_is_ignored(citation: str) -> None:
    record = _parse_csv({"PMID": "1", "Citation": citation})

    assert record.volume is None
    assert record.pages is None
    assert record.publication_date is None
