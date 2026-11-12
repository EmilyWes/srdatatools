import re

import pytest

from app.models.record import Record
from app.parsers.mapping import FieldMapping, Suggest
from app.parsers.quirks import (
    AffiliationLeadingName,
    CitationParts,
    DropEtAl,
    EmbeddedAuthorIds,
    ExpandPageRange,
    FirstValue,
    IdFromUrl,
    ParseSettings,
    RecordQuirk,
    RisNotes,
    StripDoi,
    StripLastAuthorTrailing,
    StripPmid,
    expand_page_range,
)
from tests.mappings import mapping_of

_SETTINGS = ParseSettings()


def _apply(
    quirk: RecordQuirk,
    record: Record,
    raw_fields: dict[str, str] | None = None,
    mapping: FieldMapping | None = None,
    settings: ParseSettings = _SETTINGS,
) -> Record:
    return quirk.apply(raw_fields or {}, record, mapping or FieldMapping(), settings)


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
        ("512-500", "512-500"),
    ],
)
def test_expand_page_range__expands_only_numeric_ranges_ending_lower(
    pages: str, expected: str
) -> None:
    assert expand_page_range(pages) == expected


def test_expand_page_range_quirk__expands_record_pages() -> None:
    assert _apply(ExpandPageRange(), Record(pages="521-2")).pages == "521-522"


def test_expand_page_range_quirk__without_pages_leaves_record_unchanged() -> None:
    assert _apply(ExpandPageRange(), Record()).pages is None


def test_first_value__keeps_first_line() -> None:
    record = Record(publication_type="Journal Article\nReview")

    assert _apply(FirstValue("publication_type", "\n"), record).publication_type == (
        "Journal Article"
    )


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("https://doi.org/10.1038/nature12373", "10.1038/nature12373"),
        ("doi: 10.1000/xyz-123 [doi]", "10.1000/xyz-123"),
        ("10.1000/abc", "10.1000/abc"),
        ("not a doi", "not a doi"),
    ],
)
def test_strip_doi__keeps_only_the_doi(doi: str, expected: str) -> None:
    assert _apply(StripDoi(), Record(doi=doi)).doi == expected


@pytest.mark.parametrize(
    ("pmid", "expected"),
    [
        ("https://pubmed.ncbi.nlm.nih.gov/123", "123"),
        ("PMID: 456 [pmid]", "456"),
        ("789", "789"),
        ("none", "none"),
    ],
)
def test_strip_pmid__keeps_only_the_digits(pmid: str, expected: str) -> None:
    assert _apply(StripPmid(), Record(pmid=pmid)).pmid == expected


def test_strip_doi__without_doi_leaves_record_unchanged() -> None:
    assert _apply(StripDoi(), Record()).doi is None


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("Smith J|et al.", "Smith J"),
        ("Smith J, Doe A, et al.", "Smith J, Doe A"),
        ("Smith J; et al.", "Smith J"),
        ("Smith J et al.", "Smith J"),
        ("et al.", None),
    ],
)
def test_drop_et_al__drops_trailing_et_al(names: str, expected: str | None) -> None:
    record = Record(author_names=names)

    assert _apply(DropEtAl(), record).author_names == expected


def test_drop_et_al__keeps_names_without_et_al() -> None:
    record = Record(author_names="Smith J|Petal.")

    assert _apply(DropEtAl(), record).author_names == "Smith J|Petal."


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("Smith J.|Doe A.", "Smith J.|Doe A"),
        ("Doe ...", "Doe"),
        ("Doe A.;, ", "Doe A"),
        ("Doe…", "Doe"),
        ("Doe (1).", "Doe (1)"),
    ],
)
def test_strip_last_author_trailing__strips_punctuation_and_spaces(
    names: str, expected: str
) -> None:
    record = Record(author_names=names)

    assert _apply(StripLastAuthorTrailing(), record).author_names == expected


def test_strip_last_author_trailing__without_authors_leaves_record_unchanged() -> None:
    assert _apply(StripLastAuthorTrailing(), Record()) == Record()


_EID_FROM_URL = IdFromUrl(
    key="url",
    pattern=re.compile(r"scopus\.com/pages/publications/(\d+)"),
    id_key="eid",
    prefix="2-s2.0-",
)


def test_id_from_url__adds_prefixed_id() -> None:
    raw = {"url": "https://www.scopus.com/pages/publications/105040180364"}

    record = _apply(_EID_FROM_URL, Record(other_ids={"pmc": "1"}), raw)

    assert record.other_ids == {"pmc": "1", "eid": "2-s2.0-105040180364"}


def test_id_from_url__runs_when_key_is_not_mapped() -> None:
    raw = {"url": "https://www.scopus.com/pages/publications/1"}

    record = _apply(_EID_FROM_URL, Record(), raw, FieldMapping())

    assert record.other_ids == {"eid": "2-s2.0-1"}


def test_id_from_url__without_match_leaves_record_unchanged() -> None:
    raw = {"url": "https://example.org"}

    assert _apply(_EID_FROM_URL, Record(), raw).other_ids == {}


_SCOPUS_NOTES = RisNotes(
    tag="N1",
    notes={"EID: ": "other_ids.eid", "Conference name: ": "conference_name"},
)
_NOTES = {"N1": "Export Date: 1 May 2026\nEID: 2-s2.0-1\nConference name: ICSE"}


def test_ris_notes__sets_other_id_and_fills_scalar() -> None:
    mapping = mapping_of({"N1": "notes"})

    record = _apply(_SCOPUS_NOTES, Record(), _NOTES, mapping)

    assert record.other_ids == {"eid": "2-s2.0-1"}
    assert record.conference_name == "ICSE"


def test_ris_notes__scalar_only_fills_an_empty_field() -> None:
    mapping = mapping_of({"N1": "notes"})

    record = _apply(_SCOPUS_NOTES, Record(conference_name="Mapped"), _NOTES, mapping)

    assert record.conference_name == "Mapped"


def test_ris_notes__runs_when_tag_is_not_mapped() -> None:
    record = _apply(_SCOPUS_NOTES, Record(), _NOTES, FieldMapping())

    assert record.other_ids == {"eid": "2-s2.0-1"}
    assert record.conference_name == "ICSE"


_EMBEDDED_IDS = EmbeddedAuthorIds("scopus_author_id")


_SCOPUS_AUTHORS = mapping_of(
    {
        "Author full names": Suggest("authors", {"delimiter": ";"}),
        "Author(s) ID": Suggest(
            "authors",
            {"role": "ids", "delimiter": ";", "id_key": "scopus_author_id"},
        ),
        "Authors with affiliations": Suggest(
            "authors", {"role": "affiliations", "delimiter": ";"}
        ),
    }
)


def test_embedded_author_ids__moves_ids_out_of_names() -> None:
    record = Record(author_names="Teng, Yu (60652739200); Han, Li (57190000001)")

    record = _apply(_EMBEDDED_IDS, record, mapping=_SCOPUS_AUTHORS)

    assert record.author_names == "Teng, Yu; Han, Li"
    assert record.author_ids == (
        "scopus_author_id:60652739200|scopus_author_id:57190000001"
    )


def test_embedded_author_ids__drops_ids_already_from_a_column() -> None:
    record = Record(
        author_names="Teng (1); Han (2)",
        author_ids="scopus_author_id:1|scopus_author_id:3",
    )

    record = _apply(_EMBEDDED_IDS, record, mapping=_SCOPUS_AUTHORS)

    assert record.author_ids == (
        "scopus_author_id:1|scopus_author_id:3, scopus_author_id:2"
    )


def test_embedded_author_ids__keeps_empty_slot_for_name_without_id() -> None:
    record = Record(author_names="Teng (1); Han")

    record = _apply(_EMBEDDED_IDS, record, mapping=_SCOPUS_AUTHORS)

    assert (record.author_names, record.author_ids) == (
        "Teng; Han",
        "scopus_author_id:1|",
    )


def test_embedded_author_ids__other_author_count_still_cleans_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = Record(author_names="Teng (1); Han (2)", author_ids="orcid:x")

    record = _apply(_EMBEDDED_IDS, record, mapping=_SCOPUS_AUTHORS)

    assert (record.author_names, record.author_ids) == ("Teng; Han", "orcid:x")
    assert "author names" in caplog.text


def test_embedded_author_ids__leaves_name_without_id_unchanged() -> None:
    record = Record(author_names="Teng, Yu (Jr)")

    assert _apply(_EMBEDDED_IDS, record, mapping=_SCOPUS_AUTHORS) == record


def test_embedded_author_ids__without_names_row_leaves_record_unchanged() -> None:
    record = Record(author_names="Teng (1)")

    assert _apply(_EMBEDDED_IDS, record) == record


def test_affiliation_leading_name__drops_name_before_separator() -> None:
    record = Record(
        author_affiliations=(
            "Teng Y., Guangxi Cartier Technology Ltd., Nanning; Han L.;"
            " Doe J., Utrecht University"
        )
    )

    record = _apply(AffiliationLeadingName(), record, mapping=_SCOPUS_AUTHORS)

    assert record.author_affiliations == (
        "Guangxi Cartier Technology Ltd., Nanning; Utrecht University"
    )


def test_affiliation_leading_name__only_names_leaves_no_affiliations() -> None:
    record = Record(author_affiliations="Teng Y.; Han L.")

    record = _apply(AffiliationLeadingName(), record, mapping=_SCOPUS_AUTHORS)

    assert record.author_affiliations is None


_CITATION = CitationParts("Citation")


def test_citation_parts__fills_volume_issue_and_pages() -> None:
    raw = {"Citation": "Nature. 2023 Aug;620(7974):589-594. doi: 10.1/x."}

    record = _apply(_CITATION, Record(), raw)

    assert (record.volume, record.issue, record.pages) == ("620", "7974", "589-594")


def test_citation_parts__only_fills_empty_fields() -> None:
    raw = {"Citation": "Nature. 2023 Mar;615(7950):34."}

    record = _apply(_CITATION, Record(volume="1", pages="2-3"), raw)

    assert (record.volume, record.issue, record.pages) == ("1", "7950", "2-3")


@pytest.mark.parametrize(
    "citation",
    [
        "J Ethnopharmacol. 2026 May 10;362:121354. doi: 10.1016/j.jep.2026.121354.",
        "Res Sq [Preprint]. 2023 Oct 3:rs.3.rs-3382427. doi: 10.21203/rs.3/v1.",
        "Med Sci (Paris). 2016 Nov;32 Hors série n°2:57-59. doi: 10.1051/x.",
        "2016 May 3. In: Buzsáki G, editors. Brain [Internet]. Cham: Springer; 2016.",
    ],
)
def test_citation_parts__ignores_values_not_in_the_plain_form(citation: str) -> None:
    record = _apply(_CITATION, Record(), {"Citation": citation})

    assert (record.volume, record.issue, record.pages) == (None, None, None)
