import pytest

from app.cleaning.options import CleaningOptions
from app.cleaning.steps import (
    CleaningContext,
    citation_parts,
    clean_issn_isbn,
    clean_record,
    clear_empty_values,
    drop_et_al,
    drop_trailing,
    eid_from_url,
    expand_page_range,
    file_separators,
    first_publication_type,
    id_from_name,
    pages_set,
    ris_notes,
    sniff_separator,
    split_authors,
    split_keywords,
    strip_affiliation_start,
    strip_author_extras,
    strip_doi,
    strip_pmid,
)
from app.models.record import Record
from app.parsers.mapping import FieldMapping
from tests.mappings import mapping_of

_OPTIONS = CleaningOptions()
_NO_CONTEXT = CleaningContext()


def _context(
    raw_fields: dict[str, str] | None = None,
    mapping: FieldMapping | None = None,
    use_first: tuple[str, ...] = (),
    names: str | None = None,
    affiliations: str | None = None,
    ids: str | None = None,
    keywords: str | None = None,
) -> CleaningContext:
    return CleaningContext(
        raw_fields=raw_fields or {},
        mapping=mapping or FieldMapping(),
        use_first=use_first,
        names_separator=names,
        affiliations_separator=affiliations,
        ids_separator=ids,
        keywords_separator=keywords,
    )


def _options(**changes: object) -> CleaningOptions:
    return _OPTIONS.model_copy(update=changes)


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


def test_pages_set__expands_record_pages() -> None:
    record = pages_set(Record(pages="521-2"), _NO_CONTEXT, _OPTIONS)

    assert record.pages == "521-522"


def test_pages_set__without_pages_leaves_record_unchanged() -> None:
    assert pages_set(Record(), _NO_CONTEXT, _OPTIONS) == Record()


def test_first_publication_type__keeps_first_line() -> None:
    record = Record(publication_type="Journal Article\nReview")

    cleaned = first_publication_type(record, _NO_CONTEXT, _OPTIONS)

    assert cleaned.publication_type == "Journal Article"


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
    assert strip_doi(Record(doi=doi), _NO_CONTEXT, _OPTIONS).doi == expected


def test_strip_doi__without_doi_leaves_record_unchanged() -> None:
    assert strip_doi(Record(), _NO_CONTEXT, _OPTIONS).doi is None


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
    assert strip_pmid(Record(pmid=pmid), _NO_CONTEXT, _OPTIONS).pmid == expected


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
    record = drop_et_al(Record(author_names=names), _NO_CONTEXT, _OPTIONS)

    assert record.author_names == expected


def test_drop_et_al__keeps_names_without_et_al() -> None:
    record = Record(author_names="Smith J|Petal.")

    assert drop_et_al(record, _NO_CONTEXT, _OPTIONS) == record


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("Smith J.|Doe A.", "Smith J.|Doe A"),
        ("Doe ...", "Doe"),
        ("Doe A.;, ", "Doe A"),
        ("Doe…", "Doe"),
        ("Doe (1).", "Doe (1)"),
        ("Romano M, Novacek MJ.", "Romano M, Novacek MJ"),
    ],
)
def test_drop_trailing__strips_punctuation_and_spaces(
    names: str, expected: str
) -> None:
    record = drop_trailing(Record(author_names=names), _NO_CONTEXT, _OPTIONS)

    assert record.author_names == expected


def test_drop_trailing__without_authors_leaves_record_unchanged() -> None:
    assert drop_trailing(Record(), _NO_CONTEXT, _OPTIONS) == Record()


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["Teng, Yu; Han, Li", "Doe, J"], ";"),
        (["Baron, Matthew|Norman, David"], "|"),
        (["Smith J\nDoe A"], "\n"),
        (["Smith, John and Doe, Jane"], " and "),
        (["Romano M, Novacek MJ"], None),
        ([None, ""], None),
        (["A; B|C", "D|E"], "|"),
        (["A; B|C"], "|"),
    ],
)
def test_sniff_separator__picks_the_candidate_in_most_values(
    values: list[str | None], expected: str | None
) -> None:
    assert sniff_separator(values) == expected


def test_file_separators__chosen_separator_wins_over_sniffing() -> None:
    records = [
        Record(
            author_names="A; B",
            author_affiliations="X; Y",
            author_ids="scopus_author_id:[1|2]",
            keywords=["Author:[a; b]", "[MeSH] c|d"],
        )
    ]

    assert file_separators(records, _options(names_separator=",")) == (
        ",",
        ";",
        "|",
        ";",
    )


def test_split_authors__joins_names_and_affiliations_with_bar() -> None:
    record = Record(
        author_names="Teng, Yu; Han, Li ;",
        author_affiliations="Guangxi, China ; Nanning University",
    )

    cleaned = split_authors(record, _context(names=";", affiliations=";"), _OPTIONS)

    assert cleaned.author_names == "Teng, Yu|Han, Li"
    assert cleaned.author_affiliations == "Guangxi, China|Nanning University"


def test_split_authors__value_already_split_is_left_alone() -> None:
    record = Record(author_names="Doe, J|Roe, K")

    assert split_authors(record, _context(names=","), _OPTIONS) == record


def test_split_authors__without_separator_leaves_record_unchanged() -> None:
    record = Record(author_names="Teng, Yu; Han, Li")

    assert split_authors(record, _NO_CONTEXT, _OPTIONS) == record


def test_split_authors__splits_id_column_per_author() -> None:
    record = Record(author_ids="scopus_author_id:[601; 602;603]")

    cleaned = split_authors(record, _context(ids=";"), _OPTIONS)

    assert cleaned.author_ids == (
        "scopus_author_id:601|scopus_author_id:602|scopus_author_id:603"
    )


def test_split_authors__merges_id_columns_by_position() -> None:
    record = Record(
        author_ids="openalex_author_id:[A1|A2|A3], orcid:[https://orcid.org/0-1||0-3]"
    )

    cleaned = split_authors(record, _context(ids="|"), _OPTIONS)

    assert cleaned.author_ids == (
        "openalex_author_id:A1, orcid:0-1|openalex_author_id:A2"
        "|openalex_author_id:A3, orcid:0-3"
    )


def test_split_authors__id_column_with_other_author_count_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = Record(author_ids="openalex_author_id:[A1|A2], orcid:[0-1]")

    cleaned = split_authors(record, _context(ids="|"), _OPTIONS)

    assert cleaned.author_ids == "openalex_author_id:A1|openalex_author_id:A2"
    assert "orcid" in caplog.text


def test_split_authors__without_ids_separator_the_column_is_one_author() -> None:
    record = Record(author_ids="scopus_author_id:[601]")

    cleaned = split_authors(record, _NO_CONTEXT, _OPTIONS)

    assert cleaned.author_ids == "scopus_author_id:601"


def test_split_authors__ids_already_split_are_left_alone() -> None:
    record = Record(author_ids="scopus_author_id:601|scopus_author_id:602")

    assert split_authors(record, _context(ids=";"), _OPTIONS) == record


def test_split_keywords__splits_unsplit_values_keeping_the_prefix() -> None:
    record = Record(keywords=["Author:[fossils; dinosaurs ;]", "keywords:[Humans]"])

    cleaned = split_keywords(record, _context(keywords=";"), _OPTIONS)

    assert cleaned.keywords == ["[Author] fossils", "[Author] dinosaurs", "Humans"]


def test_split_keywords__split_keywords_are_left_alone() -> None:
    record = Record(keywords=["[MeSH] Humans", "fossils; dinosaurs"])

    assert split_keywords(record, _context(keywords=";"), _OPTIONS) == record


def test_split_keywords__without_separator_the_value_is_one_keyword() -> None:
    record = Record(keywords=["keywords:[fossils; dinosaurs]"])

    cleaned = split_keywords(record, _NO_CONTEXT, _OPTIONS)

    assert cleaned.keywords == ["fossils; dinosaurs"]


def test_id_from_name__moves_ids_out_of_names() -> None:
    record = Record(author_names="Teng, Yu (60652739200)|Han, Li (57190000001)")

    record = id_from_name(record, _NO_CONTEXT, _OPTIONS)

    assert record.author_names == "Teng, Yu|Han, Li"
    assert record.author_ids == (
        "scopus_author_id:60652739200|scopus_author_id:57190000001"
    )


def test_id_from_name__adds_to_ids_already_from_a_column() -> None:
    record = Record(
        author_names="Teng (1)|Han (2)",
        author_ids="scopus_author_id:1|scopus_author_id:3",
    )

    record = id_from_name(record, _NO_CONTEXT, _OPTIONS)

    assert record.author_ids == (
        "scopus_author_id:1|scopus_author_id:3, scopus_author_id:2"
    )


def test_id_from_name__keeps_empty_slot_for_name_without_id() -> None:
    record = id_from_name(Record(author_names="Teng (1)|Han"), _NO_CONTEXT, _OPTIONS)

    assert (record.author_names, record.author_ids) == (
        "Teng|Han",
        "scopus_author_id:1|",
    )


def test_id_from_name__other_author_count_still_cleans_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    record = Record(author_names="Teng (1)|Han (2)", author_ids="orcid:x")

    record = id_from_name(record, _NO_CONTEXT, _OPTIONS)

    assert (record.author_names, record.author_ids) == ("Teng|Han", "orcid:x")
    assert "author names" in caplog.text


def test_id_from_name__leaves_name_without_numeric_id_unchanged() -> None:
    record = Record(author_names="Teng, Yu (Jr)")

    assert id_from_name(record, _NO_CONTEXT, _OPTIONS) == record


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("Teng, Yu (60652739200)|Han, Li", "Teng, Yu|Han, Li"),
        ("Doe, J [Editor]|Roe, K (Jr) ", "Doe, J|Roe, K"),
        ("Doe (A) (B)", "Doe (A)"),
        ("Doe, J", "Doe, J"),
    ],
)
def test_strip_author_extras__drops_trailing_bracketed_text(
    names: str, expected: str
) -> None:
    record = strip_author_extras(Record(author_names=names), _NO_CONTEXT, _OPTIONS)

    assert record.author_names == expected
    assert record.author_ids is None


def test_strip_affiliation_start__drops_name_before_separator() -> None:
    record = Record(
        author_names="Teng, Yu|Han, Li|Doe, Jane",
        author_affiliations=(
            "Teng Y., Guangxi Cartier Technology Ltd., Nanning|Han L."
            "|Doe J., Utrecht University"
        ),
    )

    record = strip_affiliation_start(
        record, _NO_CONTEXT, _options(affiliation_start=", ")
    )

    assert record.author_affiliations == (
        "Guangxi Cartier Technology Ltd., Nanning|Utrecht University"
    )


def test_strip_affiliation_start__only_names_leaves_no_affiliations() -> None:
    record = Record(
        author_names="Teng, Yu|Han, Li", author_affiliations="Teng Y.|Han L."
    )

    record = strip_affiliation_start(
        record, _NO_CONTEXT, _options(affiliation_start=", ")
    )

    assert record.author_affiliations is None


def test_strip_affiliation_start__keeps_affiliation_not_starting_with_the_name() -> (
    None
):
    record = Record(
        author_names="Teng, Yu|Han, Li|Roe, K",
        author_affiliations="Guangxi Ltd., Nanning|Utrecht University|Leiden, NL",
    )

    cleaned = strip_affiliation_start(
        record, _NO_CONTEXT, _options(affiliation_start=", ")
    )

    assert cleaned == record


def test_strip_affiliation_start__without_names_leaves_record_unchanged() -> None:
    record = Record(author_affiliations="Teng Y., Guangxi Ltd.")

    cleaned = strip_affiliation_start(
        record, _NO_CONTEXT, _options(affiliation_start=", ")
    )

    assert cleaned == record


_SN = "1234-5678 (electronic), 9123-4567 (print)"


@pytest.mark.parametrize(
    ("strip", "only_one", "expected"),
    [
        (True, True, "1234-5678"),
        (True, False, "1234-5678; 9123-4567"),
        (False, True, "1234-5678 (electronic)"),
    ],
)
def test_clean_issn_isbn__strip_extras_and_only_one(
    strip: bool, only_one: bool, expected: str
) -> None:
    options = _options(strip_extras=strip, only_one=only_one, preferred_qualifier="")

    assert clean_issn_isbn(Record(issn=_SN), _NO_CONTEXT, options).issn == expected


@pytest.mark.parametrize(
    "value", ["1234-5678 8765-4321", "1234-5678|8765-4321", "1234-5678\n8765-4321"]
)
def test_clean_issn_isbn__only_one_keeps_first_value(value: str) -> None:
    options = _options(preferred_qualifier="")

    assert clean_issn_isbn(Record(issn=value), _NO_CONTEXT, options).issn == (
        "1234-5678"
    )


@pytest.mark.parametrize(
    ("issn", "isbn", "expected"),
    [
        ("23330937 (ISSN)", None, ("23330937", None)),
        (None, "979-840072171-7 (ISBN)", (None, "979-840072171-7")),
        ("(Print) 1234-5678", None, ("1234-5678", None)),
    ],
)
def test_clean_issn_isbn__strip_extras_drops_qualifier(
    issn: str | None, isbn: str | None, expected: tuple[str | None, str | None]
) -> None:
    record = clean_issn_isbn(Record(issn=issn, isbn=isbn), _NO_CONTEXT, _OPTIONS)

    assert (record.issn, record.isbn) == expected


def test_clean_issn_isbn__each_field_keeps_numbers_of_its_own_length() -> None:
    value = "12345; 9783161484100; 1234-5678"

    record = clean_issn_isbn(Record(issn=value, isbn=value), _NO_CONTEXT, _OPTIONS)

    assert (record.issn, record.isbn) == ("1234-5678", "9783161484100")


def test_clean_issn_isbn__unrecognised_value_is_kept() -> None:
    record = clean_issn_isbn(Record(issn="12345"), _NO_CONTEXT, _OPTIONS)

    assert record.issn == "12345"


_IS_LINES = "1234-5678 (Print)\n8765-4321 (Electronic)\n1234-5678 (Linking)"


@pytest.mark.parametrize("preferred", ["Electronic", "electronic", " ELECTRONIC "])
def test_clean_issn_isbn__preferred_qualifier_value_wins(preferred: str) -> None:
    options = _options(preferred_qualifier=preferred)

    assert clean_issn_isbn(Record(issn=_IS_LINES), _NO_CONTEXT, options).issn == (
        "8765-4321"
    )


@pytest.mark.parametrize("preferred", ["", "Online"])
def test_clean_issn_isbn__without_matching_qualifier_first_value_wins(
    preferred: str,
) -> None:
    options = _options(preferred_qualifier=preferred)

    assert clean_issn_isbn(Record(issn=_IS_LINES), _NO_CONTEXT, options).issn == (
        "1234-5678"
    )


def test_clean_issn_isbn__preferred_qualifier_is_ignored_without_only_one() -> None:
    options = _options(only_one=False)

    assert clean_issn_isbn(Record(issn=_IS_LINES), _NO_CONTEXT, options).issn == (
        "1234-5678; 8765-4321; 1234-5678"
    )


_TITLES = mapping_of({"TI": "title", "TT": "title"})


def test_clear_empty_values__refills_from_the_next_mapped_key() -> None:
    raw = {"TI": " [not available]. ", "TT": "Translated"}
    record = Record(title=" [not available]. ")

    cleaned = clear_empty_values(record, _context(raw, _TITLES), _OPTIONS)

    assert cleaned.title == "Translated"


def test_clear_empty_values__without_refill_only_clears() -> None:
    raw = {"TI": "[Not Available].", "TT": "Translated"}
    record = Record(title="[Not Available].")
    options = _options(refill_from_raw=False)

    assert clear_empty_values(record, _context(raw, _TITLES), options).title is None


def test_clear_empty_values__nothing_to_refill_from_clears() -> None:
    record = Record(title="[Not Available].")
    context = _context({"TI": "[Not Available]."}, _TITLES)

    assert clear_empty_values(record, context, _OPTIONS).title is None


def test_clear_empty_values__refill_follows_use_first() -> None:
    mapping = mapping_of({"A": "title", "B": "title", "C": "title"})
    raw = {"A": "n/a", "B": "Second", "C": "Third"}
    context = _context(raw, mapping, use_first=("C",))
    options = _options(empty_values=["n/a"])

    cleaned = clear_empty_values(Record(title="n/a"), context, options)

    assert cleaned.title == "Third"


def test_clear_empty_values__apply_to_every_text_field() -> None:
    record = Record(title="N/A", journal="n/a", doi="10.1/x")
    options = _options(empty_values=["n/a"])

    cleaned = clear_empty_values(record, _NO_CONTEXT, options)

    assert (cleaned.title, cleaned.journal, cleaned.doi) == (None, None, "10.1/x")


def test_clear_empty_values__match_the_whole_value() -> None:
    record = Record(title="[Not Available]. A title")

    assert clear_empty_values(record, _NO_CONTEXT, _OPTIONS) == record


def test_clear_empty_values__refill_author_names_joins_lines_with_bar() -> None:
    mapping = mapping_of({"AU": "authors", "A2": "authors"})
    raw = {"AU": "n/a", "A2": "Doe, J\nRoe, K"}
    options = _options(empty_values=["n/a"])

    cleaned = clear_empty_values(
        Record(author_names="n/a"), _context(raw, mapping), options
    )

    assert cleaned.author_names == "Doe, J|Roe, K"


def test_eid_from_url__adds_prefixed_eid() -> None:
    raw = {"url": "https://www.scopus.com/pages/publications/105040180364"}

    record = eid_from_url(Record(other_ids={"pmc": "1"}), _context(raw), _OPTIONS)

    assert record.other_ids == {"pmc": "1", "eid": "2-s2.0-105040180364"}


def test_eid_from_url__reads_older_record_links() -> None:
    raw = {
        "url": "https://www.scopus.com/inward/record.uri?eid=2-s2.0-105040180364"
        "&partnerID=40"
    }

    record = eid_from_url(Record(), _context(raw), _OPTIONS)

    assert record.other_ids == {"eid": "2-s2.0-105040180364"}


def test_eid_from_url__without_match_leaves_record_unchanged() -> None:
    raw = {"url": "https://example.org"}

    assert eid_from_url(Record(), _context(raw), _OPTIONS) == Record()


_NOTES = {"N1": "Export Date: 1 May 2026\nEID: 2-s2.0-1\nConference name: ICSE"}


def test_ris_notes__sets_other_id_and_fills_empty_field() -> None:
    record = ris_notes(Record(), _context(_NOTES), _OPTIONS)

    assert record.other_ids == {"eid": "2-s2.0-1"}
    assert record.conference_name == "ICSE"


def test_ris_notes__field_already_filled_is_kept() -> None:
    record = ris_notes(Record(conference_name="Mapped"), _context(_NOTES), _OPTIONS)

    assert record.conference_name == "Mapped"


def test_ris_notes__without_labelled_notes_leaves_record_unchanged() -> None:
    context = _context({"N1": "Export Date: 22 October 2026"})

    assert ris_notes(Record(), context, _OPTIONS) == Record()


def test_citation_parts__fills_volume_issue_and_pages() -> None:
    raw = {"Citation": "Nature. 2023 Aug;620(7974):589-594. doi: 10.1/x."}

    record = citation_parts(Record(), _context(raw), _OPTIONS)

    assert (record.volume, record.issue, record.pages) == ("620", "7974", "589-594")


def test_citation_parts__only_fills_empty_fields() -> None:
    raw = {"Citation": "Nature. 2023 Mar;615(7950):34."}

    record = citation_parts(Record(volume="1", pages="2-3"), _context(raw), _OPTIONS)

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
    record = citation_parts(Record(), _context({"Citation": citation}), _OPTIONS)

    assert (record.volume, record.issue, record.pages) == (None, None, None)


_SCOPUS_RECORD = Record(
    author_names="Teng, Yu (60652739200); Han, Yiyong (59534195400)",
    author_ids="scopus_author_id:60652739200|scopus_author_id:59534195400",
    author_affiliations=(
        "Teng Y., Guangxi Cartier Technology Ltd., Nanning, China; "
        "Han Y., Nanning University, Guangxi, China"
    ),
)


def test_clean_record__scopus_authors_with_defaults_and_affiliation_start() -> None:
    options = _options(affiliation_start=", ")

    record, changed = clean_record(
        _SCOPUS_RECORD, _context(names=";", affiliations=";"), options
    )

    assert record.author_names == "Teng, Yu|Han, Yiyong"
    assert record.author_ids == (
        "scopus_author_id:60652739200|scopus_author_id:59534195400"
    )
    assert record.author_affiliations == (
        "Guangxi Cartier Technology Ltd., Nanning, China|"
        "Nanning University, Guangxi, China"
    )
    assert changed == ["Split authors", "Scopus ID from name", "Affiliation start"]


def test_clean_record__author_steps_need_split_authors() -> None:
    options = _options(split_authors=False, affiliation_start=", ")

    record, changed = clean_record(
        _SCOPUS_RECORD, _context(names=";", affiliations=";"), options
    )

    assert record == _SCOPUS_RECORD
    assert changed == []


def test_clean_record__id_from_name_runs_before_drop_trailing() -> None:
    options = _options(drop_trailing=True)

    record, _ = clean_record(
        Record(author_names="Teng (1); Han (2)"), _context(names=";"), options
    )

    assert (record.author_names, record.author_ids) == (
        "Teng|Han",
        "scopus_author_id:1|scopus_author_id:2",
    )


def test_clean_record__pages_set_expands_pages_from_citation() -> None:
    raw = {"Citation": "Rev Med Liege. 2001;56(7):521-2."}

    record, changed = clean_record(Record(), _context(raw), _OPTIONS)

    assert record.pages == "521-522"
    assert changed == ["Values from Citation", "Pages set"]


def test_clean_record__cleaning_twice_changes_nothing_more() -> None:
    context = _context(names=";", affiliations=";")
    options = _options(affiliation_start=", ", drop_trailing=True)
    once, _ = clean_record(_SCOPUS_RECORD, context, options)

    twice, changed = clean_record(once, context, options)

    assert twice == once
    assert changed == []


def test_clean_record__switched_off_steps_do_nothing() -> None:
    options = _options(
        strip_doi=False, pages_set=False, strip_extras=False, only_one=False
    )
    record = Record(doi="doi: 10.1/x", pages="521-2", issn="1234-5678 (Print)")

    assert clean_record(record, _NO_CONTEXT, options) == (record, [])
