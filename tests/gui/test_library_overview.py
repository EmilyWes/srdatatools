import json
from collections.abc import Iterator

import pytest
from nicegui import ui
from nicegui.element import Element
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.db.settings import set_setting
from app.gui.layout import shell
from app.gui.library_overview import (
    DEFAULT_SECTIONS,
    SECTIONS,
    format_count,
    load_sections,
    render_library_overview,
    render_overview_settings,
    reset_sections,
    save_sections,
    source_label,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _tables(middle: Element) -> list[ui.table]:
    return [
        element for element in middle.descendants() if isinstance(element, ui.table)
    ]


def _labels(middle: Element) -> list[str]:
    return [
        element.text
        for element in middle.descendants()
        if isinstance(element, ui.label)
    ]


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


def test_source_label__uses_profile_label() -> None:
    assert source_label("pubmed") == "PubMed"


def test_source_label__unknown_for_none() -> None:
    assert source_label(None) == "Unknown"


def test_render_library_overview__shows_total_and_one_table_per_breakdown() -> None:
    panes = shell()

    render_library_overview(
        panes.middle,
        total=3,
        per_source=[("pubmed", 2), (None, 1)],
        per_file=[("pubmed.nbib", 2), ("other.ris", 1)],
        per_year=[(2020, 2), (None, 1)],
        sections=DEFAULT_SECTIONS,
    )

    assert "3" in _labels(panes.middle)
    source_rows, file_rows, year_rows = (table.rows for table in _tables(panes.middle))
    assert source_rows == [
        {"name": "PubMed", "count": "2"},
        {"name": "Unknown", "count": "1"},
    ]
    assert file_rows == [
        {"name": "pubmed.nbib", "count": "2"},
        {"name": "other.ris", "count": "1"},
    ]
    assert year_rows == [
        {"name": "2020", "count": "2"},
        {"name": "Unknown", "count": "1"},
    ]


def test_render_library_overview__replaces_previous_middle_content() -> None:
    panes = shell()

    render_library_overview(panes.middle, 0, [], [], [], DEFAULT_SECTIONS)

    assert "Content" not in _labels(panes.middle)
    assert "0" in _labels(panes.middle)
    assert all(table.rows == [] for table in _tables(panes.middle))


def test_format_count__dot_thousands_separator() -> None:
    assert format_count(25694) == "25.694"
    assert format_count(1234567) == "1.234.567"
    assert format_count(999) == "999"


def test_render_library_overview__formats_total_and_counts() -> None:
    panes = shell()

    render_library_overview(
        panes.middle, 25694, [("pubmed", 25694)], [], [], DEFAULT_SECTIONS
    )

    assert "25.694" in _labels(panes.middle)
    assert _tables(panes.middle)[0].rows == [{"name": "PubMed", "count": "25.694"}]


def test_render_library_overview__shows_only_selected_sections() -> None:
    panes = shell()

    render_library_overview(
        panes.middle, 3, [("pubmed", 3)], [], [(2020, 3)], ["per_year"]
    )

    labels = _labels(panes.middle)
    assert "Records per year" in labels
    assert "Total records" not in labels
    assert "Records per source" not in labels
    assert "Records per file" not in labels
    assert len(_tables(panes.middle)) == 1


def test_render_library_overview__hint_when_no_sections_selected() -> None:
    panes = shell()

    render_library_overview(panes.middle, 3, [], [], [], [])

    assert _tables(panes.middle) == []
    assert _labels(panes.middle) == [
        "No sections selected. Use the gear next to Overview to choose what's shown."
    ]


def test_load_sections__defaults_when_unset(session: Session) -> None:
    assert load_sections(session) == DEFAULT_SECTIONS


def test_save_sections__roundtrip_in_display_order(session: Session) -> None:
    save_sections(session, ["per_year", "total"])
    session.commit()

    assert load_sections(session) == ["total", "per_year"]


def test_load_sections__drops_unknown_keys(session: Session) -> None:
    set_setting(session, "overview_sections", json.dumps(["total", "no_such"]))
    session.commit()

    assert load_sections(session) == ["total"]


def test_reset_sections__restores_defaults(session: Session) -> None:
    save_sections(session, ["total"])
    session.commit()

    reset_sections(session)
    session.commit()

    assert load_sections(session) == DEFAULT_SECTIONS


def test_render_overview_settings__checkboxes_reflect_sections() -> None:
    panes = shell()

    render_overview_settings(
        panes.middle, ["total"], on_change=print, on_restore=print, on_back=print
    )

    checkboxes = {
        element.text: element.value
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox)
    }
    assert len(checkboxes) == len(SECTIONS)
    assert checkboxes["Total records"] is True
    assert checkboxes["Records per year"] is False


def test_render_overview_settings__toggling_reports_new_sections() -> None:
    panes = shell()
    changes: list[list[str]] = []
    render_overview_settings(
        panes.middle,
        ["per_year"],
        on_change=changes.append,
        on_restore=lambda: None,
        on_back=lambda: None,
    )
    total_checkbox = next(
        element
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox) and element.text == "Total records"
    )

    total_checkbox.value = True

    assert changes == [["total", "per_year"]]


def test_render_overview_settings__restore_and_back_buttons_call_back() -> None:
    panes = shell()
    calls: list[str] = []
    render_overview_settings(
        panes.middle,
        ["total"],
        on_change=lambda sections: None,
        on_restore=lambda: calls.append("restore"),
        on_back=lambda: calls.append("back"),
    )

    _click(_button(panes.middle, "Restore defaults"))
    _click(_button(panes.middle, "Back to overview"))

    assert calls == ["restore", "back"]
