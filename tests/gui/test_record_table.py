import datetime
import json
from collections.abc import Iterator
from typing import Any

import pytest
from nicegui import ui
from nicegui.element import Element
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Label, Record, RecordSource, SourceFile
from app.db.settings import set_setting
from app.gui.layout import shell
from app.gui.record_table import (
    COLUMNS,
    DEFAULT_COLUMNS,
    RecordSelection,
    label_column_key,
    label_field,
    load_columns,
    load_label_columns,
    load_rows,
    render_record_table,
    render_table_settings,
    reset_columns,
    row_for,
    save_columns,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def _source_file(source: str | None) -> SourceFile:
    return SourceFile(
        filename="export.ris",
        path=None,
        format="ris",
        source=source,
        imported_at=datetime.datetime(2026, 1, 1),
        row_count=None,
    )


def _row(id_: int, **fields: Any) -> dict[str, Any]:
    return row_for({"id": id_} | fields)


def _grid(middle: Element) -> ui.aggrid:
    return next(
        element for element in middle.descendants() if isinstance(element, ui.aggrid)
    )


def _click(button: ui.button) -> None:
    click_listener = next(iter(button._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)


def _button(middle: Element, text: str) -> ui.button:
    return next(
        element
        for element in middle.descendants()
        if isinstance(element, ui.button) and element.text == text
    )


def test_load_columns__defaults_when_unset(session: Session) -> None:
    assert load_columns(session) == DEFAULT_COLUMNS


def test_save_columns__roundtrip_in_display_order(session: Session) -> None:
    save_columns(session, ["abstract", "doi"])
    session.commit()

    assert load_columns(session) == ["doi", "abstract"]


def test_load_columns__drops_unknown_keys(session: Session) -> None:
    set_setting(session, "table_columns", json.dumps(["doi", "no_such_field"]))
    session.commit()

    assert load_columns(session) == ["doi"]


def test_reset_columns__restores_defaults(session: Session) -> None:
    save_columns(session, ["abstract"])
    session.commit()

    reset_columns(session)
    session.commit()

    assert load_columns(session) == DEFAULT_COLUMNS


def test_columns__cover_every_record_field_plus_sources() -> None:
    record_fields = {column.key for column in Record.__table__.columns} - {"id"}

    assert set(COLUMNS) == record_fields | {"sources"}


def test_row_for__formats_authors_lists_and_dicts() -> None:
    row = row_for(
        {
            "id": 7,
            "authors": [{"full_name": "Smith, J"}, {"full_name": "Doe, A"}],
            "keywords": ["alpha", "beta"],
            "other_ids": {"wos": "123"},
            "publication_year": 2020,
            "doi": None,
        }
    )

    assert row == {
        "id": 7,
        "authors": "Smith, J et al.",
        "keywords": "alpha; beta",
        "other_ids": "wos: 123",
        "publication_year": 2020,
        "doi": None,
    }


def test_row_for__single_author_without_et_al() -> None:
    row = row_for({"authors": [{"family_name": "Smith", "given_name": "J"}]})

    assert row["authors"] == "Smith, J"


def test_row_for__no_authors() -> None:
    assert row_for({"authors": []})["authors"] == ""


def test_load_rows__only_requested_columns(session: Session) -> None:
    session.add(Record(id=1, title="A title", doi="10.1/x", abstract="Long text"))
    session.commit()

    assert load_rows(session, ["doi", "title"]) == [
        {"id": 1, "doi": "10.1/x", "title": "A title"}
    ]


def test_load_rows__sources_deduplicated_in_import_order(session: Session) -> None:
    session.add(
        Record(
            id=1,
            sources=[
                RecordSource(source_file=_source_file("scopus")),
                RecordSource(source_file=_source_file("pubmed")),
                RecordSource(source_file=_source_file("scopus")),
                RecordSource(source_file=_source_file(None)),
            ],
        )
    )
    session.commit()

    assert load_rows(session, ["sources"]) == [
        {"id": 1, "sources": "Scopus, PubMed, Unknown"}
    ]


def test_load_rows__record_without_sources(session: Session) -> None:
    session.add(Record(id=1))
    session.commit()

    assert load_rows(session, ["sources"]) == [{"id": 1, "sources": ""}]


def test_render_record_table__columns_follow_selection() -> None:
    panes = shell()

    render_record_table(
        panes.middle, [_row(1, doi="10.1/x")], ["doi", "title"], RecordSelection()
    )

    options = _grid(panes.middle).options
    fields = [column["field"] for column in options["columnDefs"]]
    assert fields == ["doi", "title"]
    assert options["rowData"][0]["doi"] == "10.1/x"
    assert "pagination" not in options


def test_render_record_table__restores_existing_selection() -> None:
    panes = shell()
    selection = RecordSelection(ids={1, 99})

    render_record_table(panes.middle, [_row(1), _row(2)], DEFAULT_COLUMNS, selection)

    assert selection.ids == {1}
    assert _grid(panes.middle).options["initialState"]["rowSelection"] == ["1"]


def test_record_selection__replace_with_ids() -> None:
    selection = RecordSelection(ids={5})

    selection.replace([1, 2])

    assert selection.ids == {1, 2}


def test_render_table_settings__checkboxes_reflect_columns() -> None:
    panes = shell()

    render_table_settings(
        panes.middle, ["doi"], on_change=print, on_restore=print, on_back=print
    )

    checkboxes = {
        element.text: element.value
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox)
    }
    assert len(checkboxes) == len(COLUMNS)
    assert checkboxes["DOI"] is True
    assert checkboxes["Title"] is False


def test_render_table_settings__toggling_reports_new_columns() -> None:
    panes = shell()
    changes: list[list[str]] = []
    render_table_settings(
        panes.middle,
        ["doi"],
        on_change=changes.append,
        on_restore=lambda: None,
        on_back=lambda: None,
    )
    title_checkbox = next(
        element
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox) and element.text == "Title"
    )

    title_checkbox.value = True

    assert changes == [["doi", "title"]]


def test_render_table_settings__restore_and_back_buttons_call_back() -> None:
    panes = shell()
    calls: list[str] = []
    render_table_settings(
        panes.middle,
        ["doi"],
        on_change=lambda columns: None,
        on_restore=lambda: calls.append("restore"),
        on_back=lambda: calls.append("back"),
    )

    _click(_button(panes.middle, "Restore defaults"))
    _click(_button(panes.middle, "Back to table"))

    assert calls == ["restore", "back"]


def test_render_record_table__shows_row_filter_and_selection_counts() -> None:
    panes = shell()

    render_record_table(
        panes.middle,
        [_row(1), _row(2), _row(3)],
        DEFAULT_COLUMNS,
        RecordSelection(ids={2}),
    )

    labels = [
        element.text
        for element in panes.middle.descendants()
        if isinstance(element, ui.label)
    ]
    assert labels == [
        "Total number of rows:",
        "3",
        "Rows in filter:",
        "3",
        "Rows in selection:",
        "1",
    ]


def test_render_record_table__header_checkbox_selects_filtered_rows() -> None:
    panes = shell()

    render_record_table(panes.middle, [_row(1)], DEFAULT_COLUMNS, RecordSelection())

    row_selection = _grid(panes.middle).options["rowSelection"]
    assert row_selection["headerCheckbox"] is True
    assert row_selection["selectAll"] == "filtered"


def test_render_record_table__clear_buttons_not_all_caps() -> None:
    panes = shell()

    render_record_table(panes.middle, [_row(1)], DEFAULT_COLUMNS, RecordSelection())

    for text in ("Clear all filters", "Clear selection"):
        assert "no-caps" in _button(panes.middle, text).props


def test_render_record_table__row_click_toggles_selection() -> None:
    panes = shell()

    render_record_table(panes.middle, [_row(1)], DEFAULT_COLUMNS, RecordSelection())

    row_selection = _grid(panes.middle).options["rowSelection"]
    assert row_selection["enableClickSelection"] is True
    assert row_selection["enableSelectionWithoutKeys"] is True


def test_render_record_table__counts_use_dot_thousands_separator() -> None:
    panes = shell()
    rows = [_row(id_) for id_ in range(1, 1235)]

    render_record_table(panes.middle, rows, ["doi"], RecordSelection())

    labels = [
        element.text
        for element in panes.middle.descendants()
        if isinstance(element, ui.label)
    ]
    assert labels[1] == "1.234"


TIAB = label_column_key("tiab", "Emily")
FT = label_column_key("ft", "screener 1.0")


def _add_labels(session: Session) -> None:
    source_file = _source_file(None)
    record = Record(id=1)
    session.add_all(
        [
            Label(
                record=record,
                source_file=source_file,
                phase=phase,
                screener=screener,
                value=value,
            )
            for phase, screener, value in [
                ("tiab", "Emily", "include"),
                ("tiab", "Emily", "maybe"),
                ("ft", "screener 1.0", "exclude"),
            ]
        ]
        + [Record(id=2)]
    )
    session.commit()


def test_label_field__is_free_of_dots_and_brackets() -> None:
    assert all(char.isalnum() or char == "_" for char in label_field(FT))


def test_load_label_columns__one_key_per_pair_in_library(session: Session) -> None:
    _add_labels(session)

    assert load_label_columns(session) == [TIAB, FT]


def test_load_columns__keeps_label_columns_after_fixed_ones(session: Session) -> None:
    _add_labels(session)
    save_columns(session, [FT, "doi", TIAB])
    session.commit()

    assert load_columns(session) == ["doi", TIAB, FT]


def test_load_columns__drops_label_columns_no_longer_in_library(
    session: Session,
) -> None:
    save_columns(session, ["doi", TIAB])
    session.commit()

    assert load_columns(session) == ["doi"]


def test_load_rows__label_cells_join_values_per_pair(session: Session) -> None:
    _add_labels(session)

    assert load_rows(session, [TIAB, FT]) == [
        {"id": 1, label_field(TIAB): "include; maybe", label_field(FT): "exclude"},
        {"id": 2, label_field(TIAB): "", label_field(FT): ""},
    ]


def test_render_record_table__label_column_header_and_field() -> None:
    panes = shell()

    render_record_table(panes.middle, [_row(1)], ["doi", FT], RecordSelection())

    column = _grid(panes.middle).options["columnDefs"][1]
    assert column["field"] == label_field(FT)
    assert column["headerName"] == "Label: ft / screener 1.0"
    assert column["filter"] == "agTextColumnFilter"


def test_render_table_settings__label_checkboxes_after_fixed_ones() -> None:
    panes = shell()
    changes: list[list[str]] = []
    render_table_settings(
        panes.middle,
        ["doi"],
        label_columns=[TIAB, FT],
        on_change=changes.append,
        on_restore=lambda: None,
        on_back=lambda: None,
    )
    checkboxes = [
        element
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox)
    ]

    assert [box.text for box in checkboxes[-2:]] == [
        "Label: tiab / Emily",
        "Label: ft / screener 1.0",
    ]
    assert not any(box.value for box in checkboxes[-2:])

    checkboxes[-1].value = True
    checkboxes[-2].value = True

    assert changes == [["doi", FT], ["doi", TIAB, FT]]
