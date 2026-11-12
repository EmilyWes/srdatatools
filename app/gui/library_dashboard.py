import json
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from nicegui import ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.settings import delete_setting, get_setting, set_setting
from app.gui.format import format_count, keyword_key, label_key
from app.gui.mapping_table import fill_color
from app.gui.theme import (
    CHART_COLORS,
    COMPLETE_COLOR,
    MULTIPLE_COLOR,
    OTHER_COLOR,
    UNKNOWN_COLOR,
    UU_GREEN,
    UU_ORANGE,
    UU_RED,
    UU_YELLOW,
)

_UNKNOWN = "Unknown"
_HIDDEN_KEY = "dashboard_hidden"
_COMPLETENESS = "completeness"
_DATA_QUALITY = "data_quality"
_PER_YEAR = "per_year"
_PUBLICATION_TYPE = "publication_type"
_SOURCE_FILES = "source_files"
# Same green/orange/red as the mapping's fill bars.
_FILL_COLORS = {"green": UU_GREEN, "orange": UU_ORANGE, "red": UU_RED}
_LABEL_COLORS = {
    "include": UU_GREEN,
    "exclude": UU_RED,
    "maybe": UU_YELLOW,
    "unknown": OTHER_COLOR,
    "unlabeled": UNKNOWN_COLOR,
}
_TITLE_CLASSES = "title-small self-start"
_BOX_CLASSES = "w-full h-56"
_BOX_WIDTH = "17rem"
_FRAME_CLASSES = (
    f"w-[{_BOX_WIDTH}] gap-2 items-center p-4 border outline-variant rounded-xl"
)
_TOP_KEYWORDS = 10
_TOP_TYPES = 7
_MIN_SLICE_ANGLE = 5
_COUNT_TABLE_CLASS = "dashboard-counts"
_COUNT_TABLE_CSS = (
    f".{_COUNT_TABLE_CLASS} tr, .{_COUNT_TABLE_CLASS} th,"
    f" .{_COUNT_TABLE_CLASS} td"
    " { height: 18px !important; line-height: 18px; padding-top: 0 !important;"
    " padding-bottom: 0 !important; font-size: 12px; }"
)
COMPLETENESS_FIELDS = [
    "title",
    "author_names",
    "abstract",
    "publication_date",
    "journal",
    "doi",
    "pmid",
    "keywords",
]


def _keyword_title(prefix: str | None) -> str:
    return f"Keywords: {prefix}" if prefix is not None else "Keywords"


def dashboard_items(
    label_pairs: Sequence[tuple[str, str]], keyword_prefixes: Sequence[str | None]
) -> list[tuple[str, str]]:
    return [
        (_COMPLETENESS, "Field completeness"),
        (_DATA_QUALITY, "Data quality"),
        (_PER_YEAR, "Publication year"),
        (_PUBLICATION_TYPE, "Publication type"),
        (_SOURCE_FILES, "Source files"),
        *(
            (label_key(phase, screener), f"Labels: {phase} / {screener}")
            for phase, screener in label_pairs
        ),
        *((keyword_key(prefix), _keyword_title(prefix)) for prefix in keyword_prefixes),
    ]


def load_hidden(session: Session) -> set[str]:
    stored = get_setting(session, _HIDDEN_KEY)
    return set(json.loads(stored)) if stored is not None else set()


def save_hidden(session: Session, hidden: Collection[str]) -> None:
    set_setting(session, _HIDDEN_KEY, json.dumps(sorted(hidden)))


def reset_hidden(session: Session) -> None:
    delete_setting(session, _HIDDEN_KEY)


def _fill_color(count: int, total: int) -> str:
    if total and count == total:
        return COMPLETE_COLOR
    return _FILL_COLORS[fill_color(count, total)]


def _completeness_chart(total: int, filled: Sequence[tuple[str, int]]) -> None:
    with ui.column().classes(_FRAME_CLASSES):
        ui.label("Field completeness").classes(_TITLE_CLASSES)
        ui.echart(
            {
                "grid": {"left": 8, "right": 24, "top": 8, "bottom": 8},
                "xAxis": {
                    "type": "category",
                    "data": [name for name, _ in filled],
                    "axisLabel": {"rotate": 45, "interval": 0},
                },
                "yAxis": {
                    "type": "value",
                    "max": 100,
                    "axisLabel": {"formatter": "{value}%"},
                },
                "tooltip": {
                    "trigger": "item",
                    ":formatter": "(p) => `${p.name}: ${p.data.count} / "
                    + f"{format_count(total)}`",
                },
                "series": [
                    {
                        "type": "bar",
                        "itemStyle": {"borderRadius": [4, 4, 0, 0]},
                        "data": [
                            {
                                "value": (
                                    round(100 * count / total, 1) if total else 0
                                ),
                                "count": format_count(count),
                                "itemStyle": {"color": _fill_color(count, total)},
                            }
                            for _, count in filled
                        ],
                    }
                ],
            }
        ).classes(_BOX_CLASSES)


def _year_chart(per_year: Sequence[tuple[int | None, int]]) -> None:
    counts = {year: count for year, count in per_year if year is not None}
    unknown = sum(count for year, count in per_year if year is None)
    years = list(range(min(counts), max(counts) + 1)) if counts else []
    title = "Publication year" + (
        f" ({format_count(unknown)} unknown)" if unknown else ""
    )
    with ui.column().classes(_FRAME_CLASSES):
        ui.label(title).classes(_TITLE_CLASSES)
        ui.echart(
            {
                "grid": {"left": 8, "right": 24, "top": 8, "bottom": 8},
                "xAxis": {"type": "category", "data": [str(year) for year in years]},
                "yAxis": {"type": "value", "minInterval": 1},
                "tooltip": {"trigger": "item"},
                "series": [
                    {
                        "type": "bar",
                        "color": UU_YELLOW,
                        "itemStyle": {"borderRadius": [4, 4, 0, 0]},
                        "data": [counts.get(year, 0) for year in years],
                    }
                ],
            }
        ).classes(_BOX_CLASSES)


def _pie(title: str, slices: Sequence[tuple[str, int, str]]) -> None:
    with ui.column().classes(_FRAME_CLASSES):
        ui.label(title).classes(_TITLE_CLASSES)
        ui.echart(
            {
                "tooltip": {"trigger": "item"},
                "legend": {
                    "orient": "vertical",
                    "right": 0,
                    "top": 0,
                    "textStyle": {"width": 100, "overflow": "truncate"},
                    "tooltip": {"show": True},
                },
                "series": [
                    {
                        "type": "pie",
                        "radius": "55%",
                        "center": ["25%", "55%"],
                        "minAngle": _MIN_SLICE_ANGLE,
                        "label": {"show": False},
                        "labelLine": {"show": False},
                        "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                        "data": [
                            {
                                "name": name,
                                "value": count,
                                "itemStyle": {"color": color},
                            }
                            for name, count, color in slices
                            if count
                        ],
                    }
                ],
            }
        ).classes(_BOX_CLASSES)


def _label_pie(phase: str, screener: str, counts: Mapping[str, int]) -> None:
    _pie(
        f"Labels: {phase} / {screener}",
        [
            (value, counts.get(value, 0), color)
            for value, color in _LABEL_COLORS.items()
        ],
    )


def _top_slices(counts: Sequence[tuple[str, int]]) -> list[tuple[str, int, str]]:
    top = counts[:_TOP_TYPES]
    return [
        *(
            (name, count, color)
            for (name, count), color in zip(top, CHART_COLORS, strict=False)
        ),
        ("Other", sum(count for _, count in counts[_TOP_TYPES:]), OTHER_COLOR),
    ]


def _publication_type_pie(types: Sequence[tuple[str | None, int]]) -> None:
    known = [(name, count) for name, count in types if name is not None]
    unknown = sum(count for name, count in types if name is None)
    _pie(
        "Publication type",
        [*_top_slices(known), (_UNKNOWN, unknown, UNKNOWN_COLOR)],
    )


def _source_file_pie(per_file: Sequence[tuple[str, int]], multiple: int) -> None:
    _pie(
        "Source files",
        [*_top_slices(per_file), ("Multiple files", multiple, MULTIPLE_COLOR)],
    )


def _count_table(
    title: str,
    name_label: str,
    counts: Sequence[tuple[str, int]],
    zero_is_good: bool = False,
) -> None:
    with ui.column().classes(_FRAME_CLASSES):
        ui.label(title).classes(_TITLE_CLASSES)
        table = (
            ui.table(
                columns=[
                    {
                        "name": "name",
                        "label": name_label,
                        "field": "name",
                        "align": "left",
                    },
                    {"name": "count", "label": "Records", "field": "count"},
                ],
                rows=[
                    {
                        "name": name,
                        "count": format_count(count),
                        **({"red": count > 0} if zero_is_good else {}),
                    }
                    for name, count in counts
                ],
                pagination=0,
            )
            .props("dense flat bordered hide-bottom")
            .classes(f"w-full {_COUNT_TABLE_CLASS}")
        )
        table.add_slot(
            "body-cell-name",
            '<q-td :props="props" :title="props.value"'
            ' class="ellipsis" style="max-width: 10rem">{{ props.value }}</q-td>',
        )
        if zero_is_good:
            table.add_slot(
                "body-cell-count",
                '<q-td :props="props"'
                " :class=\"props.row.red ? 'text-red' : 'text-green'\">"
                "{{ props.value }}</q-td>",
            )


def _keyword_table(prefix: str | None, counts: Sequence[tuple[str, int]]) -> None:
    _count_table(_keyword_title(prefix), "Keyword", counts[:_TOP_KEYWORDS])


def render_library_dashboard(
    middle: Element,
    total: int,
    filled: Sequence[tuple[str, int]],
    quality: Sequence[tuple[str, int]],
    per_year: Sequence[tuple[int | None, int]],
    publication_types: Sequence[tuple[str | None, int]],
    per_file: tuple[Sequence[tuple[str, int]], int],
    label_counts: Mapping[tuple[str, str], Mapping[str, int]],
    keyword_counts: Mapping[str | None, Sequence[tuple[str, int]]],
    hidden: Collection[str],
) -> None:
    pies = {
        pair: counts
        for pair, counts in label_counts.items()
        if label_key(*pair) not in hidden
    }
    keyword_tables = {
        prefix: counts
        for prefix, counts in keyword_counts.items()
        if keyword_key(prefix) not in hidden
    }
    middle.clear()
    with middle:
        with ui.column().classes("w-full p-6 gap-4"):
            if (
                _COMPLETENESS in hidden
                and _DATA_QUALITY in hidden
                and _PER_YEAR in hidden
                and _PUBLICATION_TYPE in hidden
                and _SOURCE_FILES in hidden
                and not (pies or keyword_tables)
            ):
                ui.label(
                    "Everything is hidden. Use the gear next to Dashboard to choose"
                    " what's shown."
                ).classes("text-sm text-on-surface-variant")
            with ui.grid(columns=f"repeat(auto-fill, {_BOX_WIDTH})").classes(
                "w-full gap-4 justify-evenly"
            ):
                if _COMPLETENESS not in hidden:
                    _completeness_chart(total, filled)
                if _DATA_QUALITY not in hidden:
                    _count_table("Data quality", "Check", quality, zero_is_good=True)
                if _PER_YEAR not in hidden:
                    _year_chart(per_year)
                if _PUBLICATION_TYPE not in hidden:
                    _publication_type_pie(publication_types)
                if _SOURCE_FILES not in hidden:
                    _source_file_pie(*per_file)
                for (phase, screener), counts in pies.items():
                    _label_pie(phase, screener, counts)
                for prefix, keyword_rows in keyword_tables.items():
                    _keyword_table(prefix, keyword_rows)
        ui.add_css(_COUNT_TABLE_CSS)


def render_dashboard_settings(
    middle: Element,
    items: Sequence[tuple[str, str]],
    hidden: Collection[str],
    on_change: Callable[[set[str]], Any],
    on_restore: Callable[[], Any],
    on_back: Callable[[], Any],
) -> None:
    hidden_now = set(hidden)

    def toggle(key: str, checked: bool) -> None:
        if checked:
            hidden_now.discard(key)
        else:
            hidden_now.add(key)
        on_change(set(hidden_now))

    middle.clear()
    with middle:
        with ui.column().classes("w-full p-6 gap-2"):
            ui.label("Dashboard settings").classes("text-2xl")
            ui.label("Shown").classes("title-small pt-2")
            with ui.column().classes("gap-0"):
                for key, label in items:
                    ui.checkbox(
                        label,
                        value=key not in hidden_now,
                        on_change=lambda e, key=key: toggle(key, e.value),
                    ).props("dense")
            with ui.row().classes("gap-2 pt-2"):
                ui.button("Restore defaults", color=None, on_click=on_restore).props(
                    "outline no-caps"
                )
                ui.button("Back to dashboard", color=None, on_click=on_back).props(
                    "outline no-caps"
                )
