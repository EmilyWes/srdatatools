from nicegui import ui
from nicegui.element import Element

from app.gui.layout import shell
from app.gui.library_overview import (
    format_count,
    render_library_overview,
    source_label,
)


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

    render_library_overview(panes.middle, 0, [], [], [])

    assert "Content" not in _labels(panes.middle)
    assert "0" in _labels(panes.middle)
    assert all(table.rows == [] for table in _tables(panes.middle))


def test_format_count__dot_thousands_separator() -> None:
    assert format_count(25694) == "25.694"
    assert format_count(1234567) == "1.234.567"
    assert format_count(999) == "999"


def test_render_library_overview__formats_total_and_counts() -> None:
    panes = shell()

    render_library_overview(panes.middle, 25694, [("pubmed", 25694)], [], [])

    assert "25.694" in _labels(panes.middle)
    assert _tables(panes.middle)[0].rows == [{"name": "PubMed", "count": "25.694"}]
