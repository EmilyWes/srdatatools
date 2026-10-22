from pathlib import Path

from app.parsers.bibtex import parse_bibtex_file, parse_bibtex_text
from app.parsers.mapping import FieldMapping

BIBTEX_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "general"

_MAPPING = FieldMapping(
    targets={
        "@type": "publication_type",
        "title": "title",
        "journal": "journal",
        "abstract": "abstract",
        "keywords": "keywords",
        "pages": "pages",
        "volume": "volume",
        "year": "year",
        "month": "month",
        "note": "notes",
    },
)


def test_parse_bibtex_text__maps_brace_delimited_fields() -> None:
    text = "@article{key1,\n  title = {Some Paper},\n  journal = {Nature}\n}\n"

    result = parse_bibtex_text(text, _MAPPING)

    assert result.skipped == []
    record = result.rows[0].record
    assert record.title == "Some Paper"
    assert record.journal == "Nature"


def test_parse_bibtex_text__maps_quote_delimited_fields() -> None:
    text = '@article{key1, title = "Some Paper", journal = "Nature"}'

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "Some Paper"
    assert record.journal == "Nature"


def test_parse_bibtex_text__reads_bare_values() -> None:
    text = "@article{key1, title = {T}, volume = 12, year = 2024, month = mar}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.volume == "12"
    assert record.publication_date is not None
    assert record.publication_date.year == 2024
    assert record.publication_date.month == 3


def test_parse_bibtex_text__raw_fields_include_entry_type_and_key() -> None:
    text = "@ARTICLE{Smith2024, title = {Some Paper}}"

    row = parse_bibtex_text(text, _MAPPING).rows[0]

    assert row.raw_fields == {
        "@type": "article",
        "@key": "Smith2024",
        "title": "Some Paper",
    }
    assert row.record.publication_type == "article"


def test_parse_bibtex_text__field_names_are_case_insensitive() -> None:
    text = "@article{key1, TITLE = {Some Paper}, Journal = {Nature}}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "Some Paper"
    assert record.journal == "Nature"


def test_parse_bibtex_text__raw_fields_keep_inner_braces() -> None:
    text = "@article{key1, title = {Deep Learning for {DNA} Screening}}"

    row = parse_bibtex_text(text, _MAPPING).rows[0]

    assert row.raw_fields["title"] == "Deep Learning for {DNA} Screening"
    assert row.record.title == "Deep Learning for DNA Screening"


def test_parse_bibtex_text__nested_braces_do_not_end_the_entry() -> None:
    text = "@article{key1, title = {A {B {C}} D}, journal = {Nature}}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "A B C D"
    assert record.journal == "Nature"


def test_parse_bibtex_text__commas_inside_values_do_not_split_fields() -> None:
    text = '@article{key1, title = {One, two}, journal = "Three, four"}'

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "One, two"
    assert record.journal == "Three, four"


def test_parse_bibtex_text__collapses_multiline_values() -> None:
    text = "@article{key1,\n  abstract = {First line\n\t\tsecond line.}\n}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.abstract == "First line second line."


def test_parse_bibtex_text__reads_parenthesis_delimited_entry() -> None:
    text = "@article(key1, title = {Some (short) Paper})"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "Some (short) Paper"


def test_parse_bibtex_text__allows_trailing_comma() -> None:
    text = "@article{key1, title = {Some Paper},\n}"

    result = parse_bibtex_text(text, _MAPPING)

    assert result.skipped == []
    assert result.rows[0].record.title == "Some Paper"


def test_parse_bibtex_text__ignores_text_outside_entries() -> None:
    text = "Scopus\nEXPORT DATE: 22 October 2026\n\n@article{key1, title = {T}}\n"

    result = parse_bibtex_text(text, _MAPPING)

    assert result.skipped == []
    assert len(result.rows) == 1


def test_parse_bibtex_text__ignores_comment_string_and_preamble_entries() -> None:
    text = (
        "@comment{some note}\n"
        '@string{nat = "Nature"}\n'
        '@preamble{"\\newcommand{\\x}{}"}\n'
        "@article{key1, title = {T}}\n"
    )

    result = parse_bibtex_text(text, _MAPPING)

    assert result.skipped == []
    assert [row.raw_fields["@key"] for row in result.rows] == ["key1"]


def test_parse_bibtex_text__keeps_macro_values_as_written() -> None:
    text = "@article{key1, title = {T}, journal = nat}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.journal == "nat"


def test_parse_bibtex_text__skips_entry_with_unbalanced_braces() -> None:
    text = (
        "@article{key1, title = {Fine}}\n"
        "@article{key2, title = {Broken}\n"
        "@article{key3, title = {Also fine}}\n"
    )

    result = parse_bibtex_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["Fine", "Also fine"]
    assert [(s.row_number, s.reason) for s in result.skipped] == [
        (2, "entry has unbalanced braces")
    ]


def test_parse_bibtex_text__skips_entry_without_citation_key() -> None:
    text = "@article{title = {No key}}\n@article{key2, title = {Has key}}\n"

    result = parse_bibtex_text(text, _MAPPING)

    assert [row.record.title for row in result.rows] == ["Has key"]
    assert [(s.row_number, s.reason) for s in result.skipped] == [
        (1, "entry has no citation key")
    ]


def test_parse_bibtex_text__skips_entry_without_fields() -> None:
    text = "@article{key1}\n"

    result = parse_bibtex_text(text, _MAPPING)

    assert result.rows == []
    assert [s.reason for s in result.skipped] == ["entry has no fields"]


def test_parse_bibtex_text__skips_entry_with_malformed_field() -> None:
    text = "@article{key1, title = {T}, just some words}\n"

    result = parse_bibtex_text(text, _MAPPING)

    assert result.rows == []
    assert [s.reason for s in result.skipped] == ["malformed field 'just some words'"]


def test_parse_bibtex_text__repeated_field_keeps_first() -> None:
    text = "@article{key1, title = {First}, title = {Second}}"

    row = parse_bibtex_text(text, _MAPPING).rows[0]

    assert row.raw_fields["title"] == "First"
    assert row.record.title == "First"


def test_parse_bibtex_text__handles_crlf_line_endings() -> None:
    text = "@article{key1,\r\n  title = {Some\r\n  Paper}\r\n}\r\n@article{key2,\r\n}"

    result = parse_bibtex_text(text, _MAPPING)

    assert result.rows[0].record.title == "Some Paper"
    assert [(s.row_number, s.reason) for s in result.skipped] == [
        (5, "entry has no fields")
    ]


def test_parse_bibtex_text__decodes_accent_commands() -> None:
    text = (
        "@article{key1, title = "
        "{M{\\\"u}ller \\\"{o} \\'e {\\`a} \\^{i} \\~n {\\c c} \\v{s} {\\'\\i}}}"
    )

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "Müller ö é à î ñ ç š í"


def test_parse_bibtex_text__decodes_escaped_symbols() -> None:
    text = "@article{key1, title = {R\\&D at 50\\% for \\$5 \\#1 a\\_b}}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "R&D at 50% for $5 #1 a_b"


def test_parse_bibtex_text__keeps_other_commands_as_written() -> None:
    text = "@article{key1, title = {An \\emph{important} result}}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "An \\emph important result"


def test_parse_bibtex_text__double_dash_becomes_en_dash() -> None:
    text = "@article{key1, title = {Pre--post comparison}}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.title == "Pre–post comparison"


def test_parse_bibtex_text__keeps_double_dash_in_url_and_doi() -> None:
    text = "@article{key1, url = {https://x.org/a--b}, doi = {10.1/a--b}}"
    mapping = FieldMapping(targets={"url": "url", "doi": "doi"})

    record = parse_bibtex_text(text, mapping).rows[0].record

    assert record.url == "https://x.org/a--b"
    assert record.doi == "10.1/a--b"


def test_parse_bibtex_text__normalizes_page_ranges() -> None:
    text = (
        "@article{key1, pages = {101--115}}\n"
        "@article{key2, pages = {19 - 65}}\n"
        "@article{key3, pages = {e1234}}\n"
    )

    records = [row.record for row in parse_bibtex_text(text, _MAPPING).rows]

    assert [record.pages for record in records] == ["101-115", "19-65", "e1234"]


def test_parse_bibtex_text__splits_keywords_on_list_delimiter() -> None:
    text = "@article{key1, keywords = {machine learning; systematic review}}"

    record = parse_bibtex_text(text, _MAPPING).rows[0].record

    assert record.keywords == ["machine learning", "systematic review"]


def test_parse_bibtex_file__reads_realistic_export() -> None:
    result = parse_bibtex_file(BIBTEX_FIXTURES_DIR / "bibtex_style.bib", _MAPPING)

    assert result.skipped == []
    first, second = (row.record for row in result.rows)
    assert first.publication_type == "article"
    assert first.title == "Deep Learning for DNA Screening"
    assert first.journal == "Journal of Biomedical Informatics"
    assert first.abstract == ("We evaluate neural classifiers for citation screening.")
    assert first.pages == "101-115"
    assert first.keywords == ["machine learning", "systematic review"]
    assert second.publication_type == "inproceedings"
    assert second.title == "R&D in Café Networks"
    assert second.pages == "7-9"
