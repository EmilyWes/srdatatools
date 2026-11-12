import json
from collections.abc import Iterator
from typing import Any

import pytest
from nicegui import ui
from nicegui.element import Element
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.db.settings import set_setting
from app.gui.format import keyword_key, label_key
from app.gui.layout import shell
from app.gui.library_dashboard import (
    dashboard_items,
    load_hidden,
    render_dashboard_settings,
    render_library_dashboard,
    reset_hidden,
    save_hidden,
)
from app.gui.theme import (
    CHART_COLORS,
    MULTIPLE_COLOR,
    OTHER_COLOR,
    UNKNOWN_COLOR,
    UU_GREEN,
    UU_RED,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _charts(middle: Element) -> list[ui.echart]:
    return [
        element for element in middle.descendants() if isinstance(element, ui.echart)
    ]


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


def _series_data(chart: ui.echart) -> list[Any]:
    data: list[Any] = chart.options["series"][0]["data"]
    return data


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


def _render(middle: Element, hidden: set[str] | None = None) -> None:
    render_library_dashboard(
        middle,
        total=4,
        filled=[("Title", 4), ("DOI", 3), ("Abstract", 0)],
        per_year=[(2018, 1), (2020, 2), (None, 1)],
        publication_types=[("JOUR", 3), (None, 1)],
        per_file=([("pubmed.nbib", 3)], 1),
        label_counts={
            ("tiab", "Emily"): {"include": 1, "exclude": 2, "unlabeled": 1},
            ("ft", "screener 1"): {"maybe": 4},
        },
        keyword_counts={
            None: [("Cancer", 2), ("Diet", 1)],
            "MeSH": [("Humans", 3)],
        },
        hidden=hidden or set(),
    )


def test_render_library_dashboard__completeness_as_percent_with_counts() -> None:
    panes = shell()

    _render(panes.middle)

    chart = _charts(panes.middle)[0]
    assert chart.options["xAxis"]["data"] == ["Title", "DOI", "Abstract"]
    assert _series_data(chart) == [
        {"value": 100.0, "count": "4", "itemStyle": {"color": UU_GREEN}},
        {"value": 75.0, "count": "3", "itemStyle": {"color": UU_GREEN}},
        {"value": 0.0, "count": "0", "itemStyle": {"color": UU_RED}},
    ]


def test_render_library_dashboard__completeness_with_zero_records() -> None:
    panes = shell()

    render_library_dashboard(
        panes.middle,
        0,
        [("Title", 0)],
        [],
        [],
        ([], 0),
        {},
        {},
        {"publication_type", "source_files"},
    )

    assert _series_data(_charts(panes.middle)[0]) == [
        {"value": 0, "count": "0", "itemStyle": {"color": UU_RED}}
    ]


def test_render_library_dashboard__year_chart_fills_gaps_and_omits_unknown() -> None:
    panes = shell()

    _render(panes.middle)

    chart = _charts(panes.middle)[1]
    assert chart.options["xAxis"]["data"] == ["2018", "2019", "2020"]
    assert _series_data(chart) == [1, 0, 2]
    assert "Publication year (1 unknown)" in _labels(panes.middle)


def _pie_slices(chart: ui.echart) -> list[tuple[str, int, str]]:
    return [
        (item["name"], item["value"], item["itemStyle"]["color"])
        for item in _series_data(chart)
    ]


def test_render_library_dashboard__publication_type_pie_with_unknown() -> None:
    panes = shell()

    _render(panes.middle)

    assert _pie_slices(_charts(panes.middle)[2]) == [
        ("JOUR", 3, CHART_COLORS[0]),
        ("Unknown", 1, UNKNOWN_COLOR),
    ]
    assert "Publication type" in _labels(panes.middle)


def test_render_library_dashboard__publication_type_top_seven_then_other() -> None:
    panes = shell()
    types: list[tuple[str | None, int]] = [(f"type {n}", 20 - n) for n in range(9)]

    render_library_dashboard(
        panes.middle,
        200,
        [],
        [],
        types,
        ([], 0),
        {},
        {},
        {"completeness", "per_year", "source_files"},
    )

    slices = _pie_slices(_charts(panes.middle)[0])
    assert [name for name, _, _ in slices] == [
        *(f"type {n}" for n in range(7)),
        "Other",
    ]
    assert slices[-1] == ("Other", 13 + 12, OTHER_COLOR)
    assert len({color for _, _, color in slices}) == 8


def test_render_library_dashboard__source_file_pie_with_multiple_files() -> None:
    panes = shell()

    _render(panes.middle)

    assert _pie_slices(_charts(panes.middle)[3]) == [
        ("pubmed.nbib", 3, CHART_COLORS[0]),
        ("Multiple files", 1, MULTIPLE_COLOR),
    ]
    assert "Source files" in _labels(panes.middle)


def test_render_library_dashboard__source_file_pie_top_seven_then_other() -> None:
    panes = shell()
    files = [(f"file {n}.ris", 20 - n) for n in range(8)]

    render_library_dashboard(
        panes.middle,
        200,
        [],
        [],
        [],
        (files, 0),
        {},
        {},
        {"completeness", "per_year", "publication_type"},
    )

    slices = _pie_slices(_charts(panes.middle)[0])
    assert [name for name, _, _ in slices] == [
        *(f"file {n}.ris" for n in range(7)),
        "Other",
    ]
    assert slices[-1] == ("Other", 13, OTHER_COLOR)


def test_render_library_dashboard__one_pie_per_label_pair() -> None:
    panes = shell()

    _render(panes.middle)

    tiab, ft = _charts(panes.middle)[4:]
    assert [(item["name"], item["value"]) for item in _series_data(tiab)] == [
        ("include", 1),
        ("exclude", 2),
        ("unlabeled", 1),
    ]
    assert [item["name"] for item in _series_data(ft)] == ["maybe"]
    assert "Labels: tiab / Emily" in _labels(panes.middle)


def test_render_library_dashboard__one_keyword_table_per_prefix() -> None:
    panes = shell()

    _render(panes.middle)

    default, mesh = (table.rows for table in _tables(panes.middle))
    assert default == [
        {"keyword": "Cancer", "count": "2"},
        {"keyword": "Diet", "count": "1"},
    ]
    assert mesh == [{"keyword": "Humans", "count": "3"}]
    labels = _labels(panes.middle)
    assert "Keywords" in labels
    assert "Keywords: MeSH" in labels


def test_render_library_dashboard__keyword_table_shows_top_ten_records() -> None:
    panes = shell()
    counts = [(f"keyword {n}", 20 - n) for n in range(12)]

    render_library_dashboard(
        panes.middle,
        20,
        [],
        [],
        [],
        ([], 0),
        {},
        {None: counts},
        {"completeness", "per_year", "publication_type", "source_files"},
    )

    table = _tables(panes.middle)[0]
    assert [row["keyword"] for row in table.rows] == [f"keyword {n}" for n in range(10)]
    assert [column["label"] for column in table.columns] == ["Keyword", "Records"]


def test_render_library_dashboard__skips_hidden_items() -> None:
    panes = shell()

    _render(
        panes.middle,
        {"completeness", label_key("tiab", "Emily"), keyword_key(None)},
    )

    labels = _labels(panes.middle)
    assert "Field completeness" not in labels
    assert "Labels: tiab / Emily" not in labels
    assert "Keywords" not in labels
    assert len(_charts(panes.middle)) == 4
    assert len(_tables(panes.middle)) == 1


def test_render_library_dashboard__hint_when_everything_hidden() -> None:
    panes = shell()

    render_library_dashboard(
        panes.middle,
        3,
        [],
        [],
        [],
        ([], 0),
        {},
        {},
        {"completeness", "per_year", "publication_type", "source_files"},
    )

    assert _charts(panes.middle) == []
    assert _labels(panes.middle) == [
        "Everything is hidden. Use the gear next to Dashboard to choose what's shown."
    ]


def test_render_library_dashboard__replaces_previous_middle_content() -> None:
    panes = shell()

    _render(panes.middle)

    assert "Content" not in _labels(panes.middle)


def test_dashboard_items__fixed_items_then_labels_then_keywords() -> None:
    assert dashboard_items([("ft", "screener 1")], [None, "MeSH"]) == [
        ("completeness", "Field completeness"),
        ("per_year", "Publication year"),
        ("publication_type", "Publication type"),
        ("source_files", "Source files"),
        (label_key("ft", "screener 1"), "Labels: ft / screener 1"),
        (keyword_key(None), "Keywords"),
        (keyword_key("MeSH"), "Keywords: MeSH"),
    ]


def test_load_hidden__empty_when_unset(session: Session) -> None:
    assert load_hidden(session) == set()


def test_save_hidden__roundtrip(session: Session) -> None:
    save_hidden(session, {"per_year", keyword_key("MeSH")})
    session.commit()

    assert load_hidden(session) == {"per_year", keyword_key("MeSH")}


def test_reset_hidden__shows_everything_again(session: Session) -> None:
    set_setting(session, "dashboard_hidden", json.dumps(["completeness"]))
    session.commit()

    reset_hidden(session)
    session.commit()

    assert load_hidden(session) == set()


def test_render_dashboard_settings__checkboxes_reflect_hidden() -> None:
    panes = shell()

    render_dashboard_settings(
        panes.middle,
        dashboard_items([], ["MeSH"]),
        {"per_year"},
        on_change=print,
        on_restore=print,
        on_back=print,
    )

    checkboxes = {
        element.text: element.value
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox)
    }
    assert checkboxes == {
        "Field completeness": True,
        "Publication year": False,
        "Publication type": True,
        "Source files": True,
        "Keywords: MeSH": True,
    }


def test_render_dashboard_settings__toggling_reports_hidden_items() -> None:
    panes = shell()
    changes: list[set[str]] = []
    render_dashboard_settings(
        panes.middle,
        dashboard_items([], []),
        {"per_year"},
        on_change=changes.append,
        on_restore=lambda: None,
        on_back=lambda: None,
    )
    checkbox = next(
        element
        for element in panes.middle.descendants()
        if isinstance(element, ui.checkbox) and element.text == "Field completeness"
    )

    checkbox.value = False

    assert changes == [{"completeness", "per_year"}]


def test_render_dashboard_settings__restore_and_back_buttons_call_back() -> None:
    panes = shell()
    calls: list[str] = []
    render_dashboard_settings(
        panes.middle,
        [],
        set(),
        on_change=lambda hidden: None,
        on_restore=lambda: calls.append("restore"),
        on_back=lambda: calls.append("back"),
    )

    _click(_button(panes.middle, "Restore defaults"))
    _click(_button(panes.middle, "Back to dashboard"))

    assert calls == ["restore", "back"]


def test_render_library_dashboard__pies_have_truncated_legend_top_right() -> None:
    panes = shell()

    _render(panes.middle, {"completeness", "per_year"})

    for chart in _charts(panes.middle):
        legend = chart.options["legend"]
        assert (legend["orient"], legend["right"], legend["top"]) == (
            "vertical",
            0,
            0,
        )
        assert legend["textStyle"]["overflow"] == "truncate"
        assert legend["tooltip"]["show"] is True
        assert chart.options["series"][0]["label"]["show"] is False
        assert chart.options["series"][0]["minAngle"] == 5


def test_render_library_dashboard__boxes_in_evenly_spaced_grid_with_frames() -> None:
    panes = shell()

    _render(panes.middle)

    grid = next(
        element
        for element in panes.middle.descendants()
        if isinstance(element, ui.grid)
    )
    assert grid.style["grid-template-columns"] == "repeat(auto-fill, 17rem)"
    assert "justify-evenly" in grid.classes
    frames = grid.default_slot.children
    assert len(frames) == 8
    assert all({"border", "items-center"} <= set(frame.classes) for frame in frames)
