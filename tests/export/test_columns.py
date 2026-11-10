import pytest

from app.export.columns import (
    AuthorsColumn,
    DateColumn,
    ExportColumn,
    ExportRecord,
    ExportSource,
    KeywordsColumn,
    LabelColumn,
    RawColumn,
    column_value,
    example,
    export_columns,
    fill_count,
)
from app.export.options import ExportOptions
from app.models.record import Author, Label, PartialDate, Record

_OPTIONS = ExportOptions(empty_columns=True)


def _pubmed_source(**raw_fields: str) -> ExportSource:
    return ExportSource(
        vendor="pubmed",
        filename="pubmed-deeplearni-set.nbib",
        raw_fields=raw_fields,
        ignored_keys=frozenset({"OWN", "STAT"}) & raw_fields.keys(),
    )


def _scopus_source(**raw_fields: str) -> ExportSource:
    return ExportSource(
        vendor="scopus",
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


_AUTHORS = [
    Author(family_name="LeCun", given_name="Yann"),
    Author(family_name="Bengio", given_name="Yoshua"),
    Author(full_name="Hinton Geoffrey E."),
]


def test_column_value__authors_last_first_by_default() -> None:
    record = _record(authors=_AUTHORS)

    assert _value(record, "authors") == (
        "LeCun, Yann; Bengio, Yoshua; Hinton Geoffrey E."
    )


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (
            AuthorsColumn(key="authors", label="", name="", format="first_last"),
            "Yann LeCun; Yoshua Bengio; Hinton Geoffrey E.",
        ),
        (
            AuthorsColumn(key="authors", label="", name="", format="full_name"),
            "Yann LeCun; Yoshua Bengio; Hinton Geoffrey E.",
        ),
        (
            AuthorsColumn(
                key="authors",
                label="",
                name="",
                name_separator=" ",
                author_separator=" and ",
            ),
            "LeCun Yann and Bengio Yoshua and Hinton Geoffrey E.",
        ),
    ],
)
def test_column_value__authors_options(column: AuthorsColumn, expected: str) -> None:
    assert column_value(column, _record(authors=_AUTHORS), _OPTIONS) == expected


def test_column_value__authors_full_name_format_prefers_stored_full_name() -> None:
    record = _record(
        authors=[Author(family_name="Smith", given_name="J.", full_name="Smith, John")]
    )
    column = AuthorsColumn(key="authors", label="", name="", format="full_name")

    assert column_value(column, record, _OPTIONS) == "Smith, John"


@pytest.mark.parametrize(
    ("date", "part", "expected"),
    [
        (PartialDate(year=2021), "full", "2021"),
        (PartialDate(year=2021, month=3), "full", "2021-03"),
        (PartialDate(year=2021, month=3, day=7), "full", "2021-03-07"),
        (PartialDate(year=2021, month=3, day=7), "year", "2021"),
        (PartialDate(year=2021, month=3, day=7), "month", "3"),
        (PartialDate(year=2021, month=3), "day", ""),
        (None, "full", ""),
    ],
)
def test_column_value__date_parts(
    date: PartialDate | None, part: str, expected: str
) -> None:
    column = DateColumn(key="date", label="", name="", part=part)  # type: ignore[arg-type]

    assert column_value(column, _record(publication_date=date), _OPTIONS) == expected


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
    assert "authors" not in keys


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
