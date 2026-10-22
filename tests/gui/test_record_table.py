import datetime
import json
from collections.abc import Iterator
from typing import Any

import pytest
from nicegui import ui
from nicegui.element import Element
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Record, RecordSource, SourceFile
from app.db.settings import set_setting
from app.gui.layout import shell
from app.gui.record_table import (
    COLUMNS,
    DEFAULT_COLUMNS,
    RecordSelection,
    load_columns,
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


def _record(id_: int, **fields: Any) -> Record:
    return Record(id=id_, **({"authors": [], "keywords": [], "other_ids": {}} | fields))


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


def test_row_for__formats_authors_lists_and_sources() -> None:
    record = _record(
        7,
        title="A title",
        authors=[{"full_name": "Smith, J"}, {"full_name": "Doe, A"}],
        keywords=["alpha", "beta"],
        other_ids={"wos": "123"},
        publication_year=2020,
    )
    record.sources = [
        RecordSource(source_file=_source_file("pubmed")),
        RecordSource(source_file=_source_file("pubmed")),
        RecordSource(source_file=_source_file("scopus")),
    ]

    row = row_for(record)

    assert row["id"] == 7
    assert row["authors"] == "Smith, J et al."
    assert row["keywords"] == "alpha; beta"
    assert row["other_ids"] == "wos: 123"
    assert row["publication_year"] == 2020
    assert row["sources"] == "PubMed, Scopus"


def test_row_for__single_author_without_et_al() -> None:
    record = _record(1, authors=[{"family_name": "Smith", "given_name": "J"}])

    assert row_for(record)["authors"] == "Smith, J"


def test_row_for__unknown_source_and_empty_fields() -> None:
    record = _record(1)
    record.sources = [RecordSource(source_file=_source_file(None))]

    row = row_for(record)

    assert row["sources"] == "Unknown"
    assert row["authors"] == ""
    assert row["doi"] is None


def test_render_record_table__columns_follow_selection() -> None:
    panes = shell()

    render_record_table(
        panes.middle, [_record(1, doi="10.1/x")], ["doi", "title"], RecordSelection()
    )

    options = _grid(panes.middle).options
    fields = [column["field"] for column in options["columnDefs"]]
    assert fields == ["doi", "title"]
    assert options["rowData"][0]["doi"] == "10.1/x"
    assert "pagination" not in options


def test_render_record_table__restores_existing_selection() -> None:
    panes = shell()
    selection = RecordSelection(ids={1, 99})

    render_record_table(
        panes.middle, [_record(1), _record(2)], DEFAULT_COLUMNS, selection
    )

    assert selection.ids == {1}
    assert _grid(panes.middle).options["initialState"]["rowSelection"] == ["1"]


def test_record_selection__replace_with_rows() -> None:
    selection = RecordSelection(ids={5})

    selection.replace([{"id": 1}, {"id": 2}])

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
