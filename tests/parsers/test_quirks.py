import re

import pytest

from app.models.record import Affiliation, Author, Record
from app.parsers.mapping import FieldMapping
from app.parsers.quirks import (
    AffiliationLeadingName,
    DropEtAl,
    EmbeddedAuthorIds,
    EmptyValues,
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


def test_empty_values__matches_whole_value_ignoring_case_and_spaces() -> None:
    quirk = EmptyValues("title", frozenset({"[Not Available]."}))

    assert quirk.matches(" [not available]. ")
    assert not quirk.matches("[Not Available]. A title")


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


def test_drop_et_al__drops_placeholder_author() -> None:
    record = Record(authors=[Author(full_name="Smith J"), Author(full_name="et al.")])

    assert _apply(DropEtAl(), record).authors == [Author(full_name="Smith J")]


def test_strip_last_author_trailing__strips_only_the_last_author() -> None:
    record = Record(authors=[Author(full_name="Smith J."), Author(full_name="Doe A.")])

    authors = _apply(StripLastAuthorTrailing(), record).authors

    assert [a.full_name for a in authors] == ["Smith J.", "Doe A"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Doe ...", "Doe"),
        ("Doe A.;, ", "Doe A"),
        ("Doe…", "Doe"),
        ("Doe (1).", "Doe (1)"),
    ],
)
def test_strip_last_author_trailing__strips_punctuation_and_spaces(
    name: str, expected: str
) -> None:
    record = Record(authors=[Author(full_name=name)])

    assert _apply(StripLastAuthorTrailing(), record).authors[0].full_name == expected


def test_strip_last_author_trailing__without_authors_leaves_record_unchanged() -> None:
    assert _apply(StripLastAuthorTrailing(), Record()).authors == []


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


def test_embedded_author_ids__moves_id_out_of_split_name() -> None:
    author = Author(
        full_name="Teng, Yu (60652739200)",
        family_name="Teng",
        given_name="Yu (60652739200)",
    )

    record = _apply(_EMBEDDED_IDS, Record(authors=[author]))

    assert record.authors == [
        Author(
            full_name="Teng, Yu",
            family_name="Teng",
            given_name="Yu",
            other_ids={"scopus_author_id": "60652739200"},
        )
    ]


def test_embedded_author_ids__overrides_id_from_column() -> None:
    author = Author(full_name="Teng (1)", other_ids={"scopus_author_id": "2"})

    record = _apply(_EMBEDDED_IDS, Record(authors=[author]))

    assert record.authors == [
        Author(full_name="Teng", other_ids={"scopus_author_id": "1"})
    ]


def test_embedded_author_ids__leaves_name_without_id_unchanged() -> None:
    record = Record(authors=[Author(full_name="Teng, Yu (Jr)")])

    assert _apply(_EMBEDDED_IDS, record) == record


def test_affiliation_leading_name__drops_name_before_separator() -> None:
    author = Author(
        full_name="Teng Y.",
        affiliations=[
            Affiliation(name="Teng Y., Guangxi Cartier Technology Ltd., Nanning"),
            Affiliation(name="Teng Y."),
        ],
    )

    record = _apply(AffiliationLeadingName(), Record(authors=[author]))

    assert record.authors[0].affiliations == [
        Affiliation(name="Guangxi Cartier Technology Ltd., Nanning")
    ]
