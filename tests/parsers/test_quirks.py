import re

import pytest

from app.models.record import Affiliation, Author, Record
from app.parsers.mapping import FieldMapping
from app.parsers.quirks import (
    AffiliationLeadingName,
    ContinueToNextField,
    DropEtAl,
    EmbeddedAuthorIds,
    ExpandPageRange,
    FirstValue,
    IdFromUrl,
    ParseSettings,
    RecordQuirk,
    RisNotes,
    StripLastAuthorTrailing,
    StripPrefix,
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
    ],
)
def test_expand_page_range__expands_only_abbreviated_numeric_ranges(
    pages: str, expected: str
) -> None:
    assert expand_page_range(pages) == expected


def test_expand_page_range_quirk__expands_record_pages() -> None:
    assert _apply(ExpandPageRange(), Record(pages="521-2")).pages == "521-522"


def test_expand_page_range_quirk__without_pages_leaves_record_unchanged() -> None:
    assert _apply(ExpandPageRange(), Record()).pages is None


def test_continue_to_next_field__case_sensitive_matches_exact_value_only() -> None:
    quirk = ContinueToNextField("title", frozenset({"[Not Available]."}), True)

    assert quirk.matches(" [Not Available]. ")
    assert not quirk.matches("[not available].")


def test_continue_to_next_field__case_insensitive_ignores_case() -> None:
    quirk = ContinueToNextField("title", frozenset({"No Title"}), False)

    assert quirk.matches("no title")
    assert not quirk.matches("No title given")


def test_first_value__keeps_first_of_several_values() -> None:
    record = _apply(FirstValue("issn", "|"), Record(issn="1234-5678 | 8765-4321"))

    assert record.issn == "1234-5678"


def test_first_value__keeps_first_line() -> None:
    record = Record(publication_type="Journal Article\nReview")

    assert _apply(FirstValue("publication_type", "\n"), record).publication_type == (
        "Journal Article"
    )


def test_strip_prefix__removes_prefix_only_at_the_start() -> None:
    quirk = StripPrefix("pmid", "https://pubmed.ncbi.nlm.nih.gov/")

    assert _apply(quirk, Record(pmid="https://pubmed.ncbi.nlm.nih.gov/123")).pmid == (
        "123"
    )
    assert _apply(quirk, Record(pmid="123")).pmid == "123"


def test_drop_et_al__drops_placeholder_author() -> None:
    record = Record(authors=[Author(full_name="Smith J"), Author(full_name="et al.")])

    assert _apply(DropEtAl(), record).authors == [Author(full_name="Smith J")]


def test_strip_last_author_trailing__strips_only_the_last_author() -> None:
    record = Record(authors=[Author(full_name="Smith J."), Author(full_name="Doe A.")])

    authors = _apply(StripLastAuthorTrailing("."), record).authors

    assert [a.full_name for a in authors] == ["Smith J.", "Doe A"]


def test_strip_last_author_trailing__without_authors_leaves_record_unchanged() -> None:
    assert _apply(StripLastAuthorTrailing("."), Record()).authors == []


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
