import datetime
from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import models
from app.gui.export.mapping import (
    AuthorIdKeyField,
    DateField,
    ExportField,
    ExportRecord,
    ExportSource,
    JoinedField,
    KeywordsField,
    LabelField,
    RawField,
    RisTypeField,
    example,
    export_fields,
    field_value,
    field_values,
    fill_count,
    load_export_records,
)
from app.gui.export.options import ExportOptions
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


def _column(columns: list[ExportField], key: str) -> ExportField:
    return next(column for column in columns if column.key == key)


def _value(record: ExportRecord, key: str, options: ExportOptions = _OPTIONS) -> str:
    return field_value(_column(export_fields([record], options), key), record, options)


def test_field_value__author_fields_are_separated_by_semicolon() -> None:
    record = _record(
        author_names=["LeCun, Yann", "Bengio, Yoshua"],
        author_affiliations=["NYU", "Mila"],
    )

    assert _value(record, "author_names") == "LeCun, Yann; Bengio, Yoshua"
    assert _value(record, "author_affiliations") == "NYU; Mila"


def test_field_value__authors_delimiter_option() -> None:
    record = _record(author_names=["LeCun, Yann", "Bengio, Yoshua"])
    column = JoinedField(
        key="a", label="", name="", field="author_names", delimiter=" / "
    )

    assert field_value(column, record, _OPTIONS) == "LeCun, Yann / Bengio, Yoshua"


def test_field_value__issn_isbn_delimiter_option() -> None:
    record = _record(issn=["1234-5678", "8765-4321"], isbn=["9783161484100"])
    column = JoinedField(key="i", label="", name="", field="issn", delimiter=" / ")

    assert _value(record, "issn") == "1234-5678; 8765-4321"
    assert _value(record, "isbn") == "9783161484100"
    assert field_value(column, record, _OPTIONS) == "1234-5678 / 8765-4321"


def test_export_fields__author_columns_follow_title() -> None:
    columns = export_fields([_record()], _OPTIONS)

    assert [(c.key, c.name) for c in columns[1:4]] == [
        ("title", "Title"),
        ("author_names", "Authors"),
        ("author_affiliations", "Affiliations"),
    ]


_UNSPLIT_IDS = {"orcid": ["0000-1; 0000-2"], "scopus_author_id": ["11; 22"]}


_CLEANED_IDS = {"orcid": ["1", "", ""], "scopus_author_id": ["2", "", "3"]}


def test_export_fields__author_id_keys_follow_authors() -> None:
    records = [_record(author_ids=_UNSPLIT_IDS), _record(author_ids=_CLEANED_IDS)]
    columns = export_fields(records, _OPTIONS)

    assert [(c.key, c.name) for c in columns[3:6]] == [
        ("author_ids:orcid", "orcid"),
        ("author_ids:scopus_author_id", "scopus_author_id"),
        ("author_affiliations", "Affiliations"),
    ]
    assert not any(c.key == "author_ids" for c in columns)


def test_field_value__unsplit_author_ids_per_key_as_stored() -> None:
    record = _record(author_ids=_UNSPLIT_IDS)

    assert _value(record, "author_ids:orcid") == "0000-1; 0000-2"
    assert _value(record, "author_ids:scopus_author_id") == "11; 22"


def test_field_value__cleaned_author_ids_one_slot_per_author() -> None:
    record = _record(author_ids=_CLEANED_IDS)

    assert _value(record, "author_ids:orcid") == "1; ; "
    assert _value(record, "author_ids:scopus_author_id") == "2; ; 3"


def test_field_value__cleaned_author_ids_slots_for_key_of_other_records() -> None:
    records = [
        _record(author_ids={"orcid": ["1"]}),
        _record(author_ids={"pmid": ["7", "8"]}),
    ]
    columns = export_fields(records, _OPTIONS)

    assert field_value(_column(columns, "author_ids:orcid"), records[1], _OPTIONS) == (
        "; "
    )


def test_field_value__author_ids_delimiter_option() -> None:
    record = _record(author_ids=_CLEANED_IDS)
    column = AuthorIdKeyField(
        key="a", label="", name="", id_key="scopus_author_id", delimiter=" / "
    )

    assert field_value(column, record, _OPTIONS) == "2 /  / 3"


def test_export_fields__author_id_key_clashing_with_other_id_gets_suffix() -> None:
    record = _record(author_ids={"orcid": ["0000-1"]}, other_ids={"ORCID": "x"})

    column = _column(export_fields([record], _OPTIONS), "author_ids:orcid")

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
def test_field_value__date_parts_only_from_cleaned_date(
    date: str | None, part: str, expected: str
) -> None:
    column = DateField(key="date", label="", name="", part=part)  # type: ignore[arg-type]

    assert field_value(column, _record(publication_date=date), _OPTIONS) == expected


def test_export_fields__unsplit_keywords_exported_as_stored_per_prefix() -> None:
    record = _record(keywords={"": ["deep learning; AI"], "MeSH": ["Humans; Mice"]})
    columns = export_fields([record], _OPTIONS)

    keyword_columns = [c for c in columns if isinstance(c, KeywordsField)]
    assert [c.name for c in keyword_columns] == ["Keywords", "Keywords: MeSH"]
    assert _value(record, "keywords:None") == "deep learning; AI"
    assert _value(record, "keywords:MeSH") == "Humans; Mice"


@pytest.mark.parametrize("dates", [["2021//", None], ["2021", "1998//"], ["2021"]])
def test_export_fields__year_only_dates_suggest_publication_year(
    dates: list[str | None],
) -> None:
    records = [_record(publication_date=date) for date in dates]

    column = _column(export_fields(records, _OPTIONS), "date")

    assert isinstance(column, DateField)
    assert (column.name, column.part) == ("Publication year", "year")
    assert column.label == "Publication date"


@pytest.mark.parametrize(
    "dates", [["2021//", "2021/03/"], ["Mar 2021"], [None], ["2021", "2021/03/07"]]
)
def test_export_fields__other_dates_suggest_full_publication_date(
    dates: list[str | None],
) -> None:
    records = [_record(publication_date=date) for date in dates]

    column = _column(export_fields(records, _OPTIONS), "date")

    assert isinstance(column, DateField)
    assert (column.name, column.part) == ("Publication date", "full")


def test_export_fields__one_keyword_row_per_prefix_with_prefix_stripped() -> None:
    record = _record(
        keywords={"": ["deep learning"], "MeSH": ["Humans", "Neural Networks"]}
    )
    columns = export_fields([record], _OPTIONS)

    keyword_columns = [c for c in columns if isinstance(c, KeywordsField)]
    assert [c.name for c in keyword_columns] == ["Keywords", "Keywords: MeSH"]
    assert _value(record, "keywords:None") == "deep learning"
    assert _value(record, "keywords:MeSH") == "Humans; Neural Networks"


def test_field_value__keywords_delimiter_option() -> None:
    record = _record(keywords={"MeSH": ["Humans", "Neural Networks"]})
    column = KeywordsField(key="k", label="", name="", prefix="MeSH", delimiter="|")

    assert field_value(column, record, _OPTIONS) == "Humans|Neural Networks"


def test_export_fields__one_label_row_per_phase_and_screener() -> None:
    record = _record(
        labels=[
            Label(phase="ta", screener="screener 1", value="include"),
            Label(phase="ft", screener="screener 1", value="exclude"),
            Label(phase="ta", screener="screener 1", value="maybe"),
        ]
    )
    columns = export_fields([record], _OPTIONS)

    labels = [c for c in columns if isinstance(c, LabelField)]
    assert [c.name for c in labels] == [
        "Label: ta / screener 1",
        "Label: ft / screener 1",
    ]
    assert field_value(labels[0], record, _OPTIONS) == "1; 0.5"
    words = ExportOptions(label_format="words")
    assert field_value(labels[0], record, words) == "include; maybe"


def test_field_value__unlabeled_is_empty() -> None:
    record = _record(labels=[Label(phase="ft", screener="s", value="unlabeled")])

    assert _value(record, "label:ft\x00s") == ""


def test_export_fields__one_other_id_row_per_key() -> None:
    record = _record(other_ids={"eid": "2-s2.0-85100000000", "pmcid": "PMC123"})

    assert _value(record, "other_id:eid") == "2-s2.0-85100000000"
    assert _value(record, "other_id:pmcid") == "PMC123"


def test_field_value__extras() -> None:
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


def test_field_value__sources_lists_each_of_a_files_sources() -> None:
    source = replace(_pubmed_source(TI="A"), vendors=("pubmed", "asreview"))

    assert _value(_record(sources=[source]), "sources") == "PubMed, ASReview"


def test_field_value__file_without_sources_is_unknown() -> None:
    source = replace(_pubmed_source(TI="A"), vendors=())

    assert _value(_record(sources=[source]), "sources") == "Unknown"


def test_export_fields__no_raw_rows_by_default() -> None:
    record = _record(sources=[_scopus_source(Title="A", Link="https://x")])

    columns = export_fields([record], _OPTIONS)

    assert not any(isinstance(c, RawField) for c in columns)


def test_export_fields__ignored_columns_adds_only_ignored_raw_keys() -> None:
    records = [
        _record(sources=[_scopus_source(Title="A", Link="https://x")]),
        _record(id=2, sources=[_pubmed_source(TI="B", OWN="NLM")]),
    ]

    columns = export_fields(records, ExportOptions(ignored_columns=True))

    raw = [c for c in columns if isinstance(c, RawField)]
    assert [(c.label, c.name) for c in raw] == [
        ("Original: Link", "Link"),
        ("Original: OWN", "OWN"),
    ]


def test_export_fields__original_data_adds_every_raw_key_and_marks_clashes() -> None:
    record = _record(sources=[_scopus_source(Title="A", Link="https://x")])

    columns = export_fields([record], ExportOptions(original_data=True))

    raw = [c for c in columns if isinstance(c, RawField)]
    assert [c.name for c in raw] == ["Title (original)", "Link"]
    assert columns[-len(raw) :] == raw


def test_field_value__raw_joins_distinct_values_across_sources() -> None:
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


def test_export_fields__leaves_out_empty_columns_by_default() -> None:
    records = [_record(title="A", doi="10.1/x"), _record(id=2, title="B")]

    columns = export_fields(records, ExportOptions())

    keys = [column.key for column in columns]
    assert "title" in keys
    assert "doi" in keys
    assert "abstract" not in keys
    assert "author_names" not in keys


def test_export_fields__empty_columns_option_keeps_them() -> None:
    columns = export_fields([_record(title="A")], ExportOptions(empty_columns=True))

    assert "abstract" in [column.key for column in columns]


def test_fill_count_and_example__count_records_with_a_value() -> None:
    records = [
        _record(id=1),
        _record(id=2, doi="10.1038/nature14539"),
        _record(id=3, doi="10.1109/5.726791"),
    ]
    column = _column(export_fields(records, _OPTIONS), "doi")

    assert fill_count(column, records, _OPTIONS) == 2
    assert example(column, records, _OPTIONS) == "10.1038/nature14539"


_RIS = ExportOptions(file_type="ris", empty_columns=True)


def _ris_field(key: str, records: list[ExportRecord] | None = None) -> ExportField:
    return _column(export_fields(records or [_record()], _RIS), key)


@pytest.mark.parametrize(
    ("key", "tag"),
    [
        ("record_id", "ID"),
        ("title", "TI"),
        ("author_names", "AU"),
        ("author_affiliations", "AD"),
        ("date:year", "PY"),
        ("date", "DA"),
        ("journal", "T2"),
        ("conference_name", "T2"),
        ("volume", "VL"),
        ("issue", "IS"),
        ("pages:start", "SP"),
        ("pages:end", "EP"),
        ("abstract", "AB"),
        ("doi", "DO"),
        ("pmid", "AN"),
        ("issn", "SN"),
        ("isbn", "SN"),
        ("keywords:None", "KW"),
        ("language", "LA"),
        ("publisher", "PB"),
        ("url", "UR"),
    ],
)
def test_export_fields__ris_default_tags(key: str, tag: str) -> None:
    column = _ris_field(key)

    assert column.name == tag
    assert column.default_checked


def test_export_fields__ris_type_row_first() -> None:
    column = export_fields([_record()], _RIS)[0]

    assert isinstance(column, RisTypeField)
    assert column.name == "TY"


def test_export_fields__ris_notes_row_is_n1_without_note_name() -> None:
    column = _ris_field("notes")

    assert (column.name, column.note_name) == ("N1", "")


def test_export_fields__ris_keyword_prefix_rows_are_kw() -> None:
    record = _record(keywords={"Author": ["fossils"]})

    assert _ris_field("keywords:Author", [record]).name == "KW"


def test_export_fields__ris_pages_one_sp_row_without_split() -> None:
    options = _RIS.model_copy(update={"split_pages": False})
    keys = [c.key for c in export_fields([_record()], options)]

    assert "pages" in keys
    assert "pages:start" not in keys
    assert _column(export_fields([_record()], options), "pages").name == "SP"


@pytest.mark.parametrize(
    ("key", "note_name", "checked"),
    [
        ("other_id:eid", "eid", True),
        ("label:ta\x00screener 1", "Label: ta / screener 1", True),
        ("author_ids:orcid", "Author IDs: orcid", False),
        ("sources", "Sources", False),
        ("source_files", "Source files", False),
    ],
)
def test_export_fields__ris_rows_without_a_tag_go_to_n1(
    key: str, note_name: str, checked: bool
) -> None:
    record = _record(
        other_ids={"eid": "2-s2.0-1"},
        labels=[Label(phase="ta", screener="screener 1", value="include")],
        author_ids={"orcid": ["1"]},
    )

    column = _ris_field(key, [record])

    assert (column.name, column.note_name) == ("N1", note_name)
    assert column.default_checked is checked


def test_export_fields__ris_raw_keys_keep_tag_or_go_to_n1() -> None:
    record = _record(sources=[_scopus_source(**{"M3": "Article", "Cited by": "4"})])
    options = _RIS.model_copy(update={"original_data": True})
    columns = export_fields([record], options)

    tagged = _column(columns, "raw:M3")
    other = _column(columns, "raw:Cited by")
    assert (tagged.name, tagged.note_name) == ("M3", "")
    assert (other.name, other.note_name) == ("N1", "Cited by")
    assert tagged.default_checked and other.default_checked


@pytest.mark.parametrize(
    ("pages", "start", "end"),
    [("12-34", "12", "34"), ("e123", "e123", ""), (None, "", "")],
)
def test_field_value__ris_pages_split(pages: str | None, start: str, end: str) -> None:
    record = _record(pages=pages)

    assert field_value(_ris_field("pages:start"), record, _RIS) == start
    assert field_value(_ris_field("pages:end"), record, _RIS) == end


@pytest.mark.parametrize(
    ("date", "year", "ris_date"),
    [
        ("2021/03/07", "2021", "2021/03/07/"),
        ("2021/03/", "2021", "2021/03//"),
        ("2021//", "2021", "2021///"),
        ("Mar 2021", "", "Mar 2021"),
        (None, "", ""),
    ],
)
def test_field_value__ris_year_and_date(
    date: str | None, year: str, ris_date: str
) -> None:
    record = _record(publication_date=date)

    assert field_value(_ris_field("date:year"), record, _RIS) == year
    assert field_value(_ris_field("date"), record, _RIS) == ris_date


def test_field_value__ris_cleaned_dates_only_leaves_out_uncleaned() -> None:
    options = _RIS.model_copy(update={"cleaned_dates_only": True})
    column = _ris_field("date")

    assert field_value(column, _record(publication_date="Mar 2021"), options) == ""
    assert field_value(column, _record(publication_date="2021//"), options) == (
        "2021///"
    )


@pytest.mark.parametrize(
    ("stored", "code"), [("Article", "JOUR"), ("CPAPER", "CPAPER"), (None, "GEN")]
)
def test_field_value__ris_type(stored: str | None, code: str) -> None:
    record = _record(publication_type=stored)

    assert field_value(_ris_field("publication_type"), record, _RIS) == code


def test_field_values__one_value_per_author_keyword_and_label() -> None:
    record = _record(
        author_names=["LeCun, Yann", "Bengio, Yoshua"],
        keywords={"": ["fossils", "dinosaurs"]},
        labels=[
            Label(phase="ta", screener="s", value="include"),
            Label(phase="ta", screener="s", value="maybe"),
        ],
    )
    columns = export_fields([record], _RIS)

    def values(key: str) -> list[str]:
        return field_values(_column(columns, key), record, _RIS)

    assert values("author_names") == ["LeCun, Yann", "Bengio, Yoshua"]
    assert values("keywords:None") == ["fossils", "dinosaurs"]
    assert values("label:ta\x00s") == ["1", "0.5"]


def test_field_values__cleaned_author_ids_skip_empty_slots() -> None:
    record = _record(author_ids=_CLEANED_IDS)
    column = _ris_field("author_ids:scopus_author_id", [record])

    assert field_values(column, record, _RIS) == ["2", "3"]


@pytest.mark.parametrize("value", ["A title", None])
def test_field_values__single_value_or_none(value: str | None) -> None:
    record = _record(title=value)

    expected = [value] if value else []
    assert field_values(_ris_field("title"), record, _RIS) == expected


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def _orm_source_file(
    filename: str, source: str | None, imported_at: datetime.datetime
) -> models.SourceFile:
    return models.SourceFile(
        filename=filename,
        path=None,
        format="ris",
        sources=[source] if source is not None else [],
        imported_at=imported_at,
        row_count=None,
    )


def _mapped_file(
    filename: str, source: str | None, mapped: list[str]
) -> models.SourceFile:
    source_file = _orm_source_file(filename, source, datetime.datetime(2026, 1, 1))
    source_file.field_mapping = {"rows": {key: {"target": "title"} for key in mapped}}
    return source_file


def test_load_export_records__builds_record_sources_and_labels(
    session: Session,
) -> None:
    scopus = _mapped_file("scopus.csv", "scopus", ["Title"])
    record = models.Record(
        title="Deep learning",
        author_names=["LeCun, Yann"],
        publication_date="2015/05/",
        doi="10.1038/nature14539",
        keywords={"MeSH": ["Humans"]},
        other_ids={"eid": "2-s2.0-1"},
        sources=[
            models.RecordSource(
                source_file=scopus,
                raw_fields={"Title": "Deep learning", "Link": "https://x"},
            )
        ],
        labels=[
            models.Label(source_file=scopus, phase="ft", screener="s1", value="include")
        ],
    )
    session.add(record)
    session.commit()

    [export] = load_export_records(session)

    assert export.id == record.id
    assert export.record.title == "Deep learning"
    assert export.record.author_names == ["LeCun, Yann"]
    assert export.record.publication_date == "2015/05/"
    assert export.record.keywords == {"MeSH": ["Humans"]}
    assert export.record.other_ids == {"eid": "2-s2.0-1"}
    assert [(lb.phase, lb.screener, lb.value) for lb in export.record.labels] == [
        ("ft", "s1", "include")
    ]
    [source] = export.sources
    assert (source.vendors, source.filename) == (("scopus",), "scopus.csv")
    assert source.raw_fields == {"Title": "Deep learning", "Link": "https://x"}
    assert source.ignored_keys == {"Link"}


def test_load_export_records__no_date_when_no_parts(session: Session) -> None:
    session.add(models.Record(title="Undated"))
    session.commit()

    [export] = load_export_records(session)

    assert export.record.publication_date is None


def test_load_export_records__only_the_given_ids(session: Session) -> None:
    pubmed = _mapped_file("pubmed.nbib", "pubmed", ["TI"])
    records = [
        models.Record(
            title=title,
            sources=[models.RecordSource(source_file=pubmed, raw_fields={"TI": title})],
            labels=[
                models.Label(
                    source_file=pubmed, phase="ft", screener="s1", value="exclude"
                )
            ],
        )
        for title in ("A", "B", "C")
    ]
    session.add_all(records)
    session.commit()

    result = load_export_records(session, {records[0].id, records[2].id})

    assert [export.record.title for export in result] == ["A", "C"]
    assert all(len(export.sources) == 1 for export in result)
    assert all(len(export.record.labels) == 1 for export in result)
