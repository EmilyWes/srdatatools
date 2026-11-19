from dataclasses import replace

import pytest

from app.export.columns import (
    AuthorIdKeyColumn,
    DateColumn,
    ExportColumn,
    ExportRecord,
    ExportSource,
    JoinedColumn,
    KeywordsColumn,
    LabelColumn,
    RawColumn,
    column_value,
    example,
    export_columns,
    fill_count,
)
from app.export.options import ExportOptions
from app.models.record import Label, Record

_OPTIONS = ExportOptions(empty_columns=True)


def _pubmed_source(**raw_fields: str) -> ExportSource:
    return ExportSource(
        vendors=("pubmed",),
        filename="pubmed-deeplearni-set.nbib",
        raw_fields=raw_fields,
        ignored_keys=frozenset({"OWN", "STAT"}) & raw_fields.keys(),
    )


def _scopus_source(**raw_fields: str) -> ExportSource:
    return ExportSource(
        vendors=("scopus",),
        filename="scopus.csv",
        raw_fields=raw_fields,
        ignored_keys=frozenset({"Link", "Source"}) & raw_fields.keys(),
    )


def _record(**fields: object) -> ExportRecord:
    sources = fields.pop("sources", [])
    record_id = fields.pop("id", 1)
    return ExportRecord(
        id=record_id,  # type: ignore[arg-type]
        record=Record.model_validate(fields),
        sources=sources,  # type: ignore[arg-type]
    )


def _column(columns: list[ExportColumn], key: str) -> ExportColumn:
    return next(column for column in columns if column.key == key)


def _value(record: ExportRecord, key: str, options: ExportOptions = _OPTIONS) -> str:
    return column_value(
        _column(export_columns([record], options), key), record, options
    )


def test_column_value__author_fields_are_separated_by_semicolon() -> None:
    record = _record(
        author_names="LeCun, Yann|Bengio, Yoshua",
        author_affiliations="NYU|Mila",
    )

    assert _value(record, "author_names") == "LeCun, Yann; Bengio, Yoshua"
    assert _value(record, "author_affiliations") == "NYU; Mila"


def test_column_value__authors_delimiter_option() -> None:
    record = _record(author_names="LeCun, Yann|Bengio, Yoshua")
    column = JoinedColumn(
        key="a", label="", name="", field="author_names", delimiter=" / "
    )

    assert column_value(column, record, _OPTIONS) == "LeCun, Yann / Bengio, Yoshua"


def test_column_value__issn_isbn_delimiter_option() -> None:
    record = _record(issn="1234-5678|8765-4321", isbn="9783161484100")
    column = JoinedColumn(key="i", label="", name="", field="issn", delimiter=" / ")

    assert _value(record, "issn") == "1234-5678; 8765-4321"
    assert _value(record, "isbn") == "9783161484100"
    assert column_value(column, record, _OPTIONS) == "1234-5678 / 8765-4321"


def test_export_columns__author_columns_follow_title() -> None:
    columns = export_columns([_record()], _OPTIONS)

    assert [(c.key, c.name) for c in columns[1:4]] == [
        ("title", "Title"),
        ("author_names", "Authors"),
        ("author_affiliations", "Affiliations"),
    ]


_UNSPLIT_IDS = "orcid:[0000-1; 0000-2], scopus_author_id:[11; 22]"


_CLEANED_IDS = "orcid:1, scopus_author_id:2||scopus_author_id:3"


def test_export_columns__author_id_keys_follow_authors() -> None:
    records = [_record(author_ids=_UNSPLIT_IDS), _record(author_ids=_CLEANED_IDS)]
    columns = export_columns(records, _OPTIONS)

    assert [(c.key, c.name) for c in columns[3:6]] == [
        ("author_ids:orcid", "orcid"),
        ("author_ids:scopus_author_id", "scopus_author_id"),
        ("author_affiliations", "Affiliations"),
    ]
    assert not any(c.key == "author_ids" for c in columns)


def test_column_value__unsplit_author_ids_per_key_as_stored() -> None:
    record = _record(author_ids=_UNSPLIT_IDS)

    assert _value(record, "author_ids:orcid") == "0000-1; 0000-2"
    assert _value(record, "author_ids:scopus_author_id") == "11; 22"


def test_column_value__cleaned_author_ids_one_slot_per_author() -> None:
    record = _record(author_ids=_CLEANED_IDS)

    assert _value(record, "author_ids:orcid") == "1; ; "
    assert _value(record, "author_ids:scopus_author_id") == "2; ; 3"


def test_column_value__cleaned_author_ids_slots_for_key_of_other_records() -> None:
    records = [_record(author_ids="orcid:1"), _record(author_ids="pmid:7|pmid:8")]
    columns = export_columns(records, _OPTIONS)

    assert column_value(_column(columns, "author_ids:orcid"), records[1], _OPTIONS) == (
        "; "
    )


def test_column_value__author_ids_delimiter_option() -> None:
    record = _record(author_ids=_CLEANED_IDS)
    column = AuthorIdKeyColumn(
        key="a", label="", name="", id_key="scopus_author_id", delimiter=" / "
    )

    assert column_value(column, record, _OPTIONS) == "2 /  / 3"


def test_export_columns__author_id_key_clashing_with_other_id_gets_suffix() -> None:
    record = _record(author_ids="orcid:[0000-1]", other_ids={"ORCID": "x"})

    column = _column(export_columns([record], _OPTIONS), "author_ids:orcid")

    assert column.name == "orcid (author IDs)"


@pytest.mark.parametrize(
    ("date", "part", "expected"),
    [
        ("2021//", "full", "2021//"),
        ("Mar 2021", "full", "Mar 2021"),
        ("2021/03/07", "year", "2021"),
        ("2021/03/07", "month", "3"),
        ("2021/03/", "day", ""),
        ("Mar 2021", "year", ""),
        ("2021", "year", "2021"),
        ("2021", "month", ""),
        (None, "full", ""),
    ],
)
def test_column_value__date_parts_only_from_cleaned_date(
    date: str | None, part: str, expected: str
) -> None:
    column = DateColumn(key="date", label="", name="", part=part)  # type: ignore[arg-type]

    assert column_value(column, _record(publication_date=date), _OPTIONS) == expected


def test_export_columns__unsplit_keywords_exported_as_stored_per_prefix() -> None:
    record = _record(keywords=["keywords:[deep learning; AI]", "MeSH:[Humans; Mice]"])
    columns = export_columns([record], _OPTIONS)

    keyword_columns = [c for c in columns if isinstance(c, KeywordsColumn)]
    assert [c.name for c in keyword_columns] == ["Keywords", "Keywords: MeSH"]
    assert _value(record, "keywords:None") == "deep learning; AI"
    assert _value(record, "keywords:MeSH") == "Humans; Mice"


@pytest.mark.parametrize("dates", [["2021//", None], ["2021", "1998//"], ["2021"]])
def test_export_columns__year_only_dates_suggest_publication_year(
    dates: list[str | None],
) -> None:
    records = [_record(publication_date=date) for date in dates]

    column = _column(export_columns(records, _OPTIONS), "date")

    assert isinstance(column, DateColumn)
    assert (column.name, column.part) == ("Publication year", "year")
    assert column.label == "Publication date"


@pytest.mark.parametrize(
    "dates", [["2021//", "2021/03/"], ["Mar 2021"], [None], ["2021", "2021/03/07"]]
)
def test_export_columns__other_dates_suggest_full_publication_date(
    dates: list[str | None],
) -> None:
    records = [_record(publication_date=date) for date in dates]

    column = _column(export_columns(records, _OPTIONS), "date")

    assert isinstance(column, DateColumn)
    assert (column.name, column.part) == ("Publication date", "full")


def test_export_columns__one_keyword_row_per_prefix_with_prefix_stripped() -> None:
    record = _record(
        keywords=["deep learning", "[MeSH] Humans", "[MeSH] Neural Networks"]
    )
    columns = export_columns([record], _OPTIONS)

    keyword_columns = [c for c in columns if isinstance(c, KeywordsColumn)]
    assert [c.name for c in keyword_columns] == ["Keywords", "Keywords: MeSH"]
    assert _value(record, "keywords:None") == "deep learning"
    assert _value(record, "keywords:MeSH") == "Humans; Neural Networks"


def test_column_value__keywords_delimiter_option() -> None:
    record = _record(keywords=["[MeSH] Humans", "[MeSH] Neural Networks"])
    column = KeywordsColumn(key="k", label="", name="", prefix="MeSH", delimiter="|")

    assert column_value(column, record, _OPTIONS) == "Humans|Neural Networks"


def test_export_columns__one_label_row_per_phase_and_screener() -> None:
    record = _record(
        labels=[
            Label(phase="ta", screener="screener 1", value="include"),
            Label(phase="ft", screener="screener 1", value="exclude"),
            Label(phase="ta", screener="screener 1", value="maybe"),
        ]
    )
    columns = export_columns([record], _OPTIONS)

    labels = [c for c in columns if isinstance(c, LabelColumn)]
    assert [c.name for c in labels] == [
        "Label: ta / screener 1",
        "Label: ft / screener 1",
    ]
    assert column_value(labels[0], record, _OPTIONS) == "1; 0.5"
    words = ExportOptions(label_format="words")
    assert column_value(labels[0], record, words) == "include; maybe"


def test_column_value__unlabeled_is_empty() -> None:
    record = _record(labels=[Label(phase="ft", screener="s", value="unlabeled")])

    assert _value(record, "label:ft\x00s") == ""


def test_export_columns__one_other_id_row_per_key() -> None:
    record = _record(other_ids={"eid": "2-s2.0-85100000000", "pmcid": "PMC123"})

    assert _value(record, "other_id:eid") == "2-s2.0-85100000000"
    assert _value(record, "other_id:pmcid") == "PMC123"


def test_column_value__extras() -> None:
    record = _record(
        id=42,
        sources=[
            _pubmed_source(TI="A"),
            _scopus_source(Title="A"),
            _pubmed_source(TI="A"),
        ],
    )

    assert _value(record, "record_id") == "42"
    assert _value(record, "sources") == "PubMed, Scopus"
    assert _value(record, "source_files") == ("pubmed-deeplearni-set.nbib; scopus.csv")


def test_column_value__sources_lists_each_of_a_files_sources() -> None:
    source = replace(_pubmed_source(TI="A"), vendors=("pubmed", "asreview"))

    assert _value(_record(sources=[source]), "sources") == "PubMed, ASReview"


def test_column_value__file_without_sources_is_unknown() -> None:
    source = replace(_pubmed_source(TI="A"), vendors=())

    assert _value(_record(sources=[source]), "sources") == "Unknown"


def test_export_columns__no_raw_rows_by_default() -> None:
    record = _record(sources=[_scopus_source(Title="A", Link="https://x")])

    columns = export_columns([record], _OPTIONS)

    assert not any(isinstance(c, RawColumn) for c in columns)


def test_export_columns__ignored_columns_adds_only_ignored_raw_keys() -> None:
    records = [
        _record(sources=[_scopus_source(Title="A", Link="https://x")]),
        _record(id=2, sources=[_pubmed_source(TI="B", OWN="NLM")]),
    ]

    columns = export_columns(records, ExportOptions(ignored_columns=True))

    raw = [c for c in columns if isinstance(c, RawColumn)]
    assert [(c.label, c.name) for c in raw] == [
        ("Original: Link", "Link"),
        ("Original: OWN", "OWN"),
    ]


def test_export_columns__original_data_adds_every_raw_key_and_marks_clashes() -> None:
    record = _record(sources=[_scopus_source(Title="A", Link="https://x")])

    columns = export_columns([record], ExportOptions(original_data=True))

    raw = [c for c in columns if isinstance(c, RawColumn)]
    assert [c.name for c in raw] == ["Title (original)", "Link"]
    assert columns[-len(raw) :] == raw


def test_column_value__raw_joins_distinct_values_across_sources() -> None:
    record = _record(
        sources=[
            _scopus_source(Source="Scopus"),
            _scopus_source(Source="Scopus"),
            _scopus_source(Source="Scopus AI"),
            _scopus_source(Title="no Source key"),
        ]
    )
    options = ExportOptions(original_data=True)

    assert _value(record, "raw:Source", options) == "Scopus; Scopus AI"


def test_export_columns__leaves_out_empty_columns_by_default() -> None:
    records = [_record(title="A", doi="10.1/x"), _record(id=2, title="B")]

    columns = export_columns(records, ExportOptions())

    keys = [column.key for column in columns]
    assert "title" in keys
    assert "doi" in keys
    assert "abstract" not in keys
    assert "author_names" not in keys


def test_export_columns__empty_columns_option_keeps_them() -> None:
    columns = export_columns([_record(title="A")], ExportOptions(empty_columns=True))

    assert "abstract" in [column.key for column in columns]


def test_fill_count_and_example__count_records_with_a_value() -> None:
    records = [
        _record(id=1),
        _record(id=2, doi="10.1038/nature14539"),
        _record(id=3, doi="10.1109/5.726791"),
    ]
    column = _column(export_columns(records, _OPTIONS), "doi")

    assert fill_count(column, records, _OPTIONS) == 2
    assert example(column, records, _OPTIONS) == "10.1038/nature14539"
