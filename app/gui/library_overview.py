import json
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from nicegui import ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.settings import delete_setting, get_setting, set_setting
from app.parsers.profiles import PROFILES

_UNKNOWN = "Unknown"
_HIDDEN_KEY = "overview_hidden"
_COMPLETENESS = "completeness"
_PER_YEAR = "per_year"
_BAR_COLOR = "#5470c6"
_LABEL_COLORS = {
    "include": "#21ba45",
    "exclude": "#c10015",
    "maybe": "#f2c037",
    "unknown": "#9e9e9e",
    "unlabeled": "#e0e0e0",
}
_TITLE_CLASSES = "text-sm text-grey-7"
_BOX_CLASSES = "w-96 h-80"
_TOP_KEYWORDS = 10
COMPLETENESS_FIELDS = [
    "title",
    "authors",
    "abstract",
    "publication_year",
    "journal",
    "doi",
    "pmid",
    "keywords",
]


def label_item_key(phase: str, screener: str) -> str:
    return "label:" + json.dumps([phase, screener])


def keyword_item_key(prefix: str | None) -> str:
    return "keywords:" + json.dumps(prefix)


def _keyword_title(prefix: str | None) -> str:
    return f"Keywords: {prefix}" if prefix is not None else "Keywords"


def overview_items(
    label_pairs: Sequence[tuple[str, str]], keyword_prefixes: Sequence[str | None]
) -> list[tuple[str, str]]:
    return [
        (_COMPLETENESS, "Field completeness"),
        (_PER_YEAR, "Publication year"),
        *(
            (label_item_key(phase, screener), f"Labels: {phase} / {screener}")
            for phase, screener in label_pairs
        ),
        *(
            (keyword_item_key(prefix), _keyword_title(prefix))
            for prefix in keyword_prefixes
        ),
    ]


def load_hidden(session: Session) -> set[str]:
    stored = get_setting(session, _HIDDEN_KEY)
    return set(json.loads(stored)) if stored is not None else set()


def save_hidden(session: Session, hidden: Collection[str]) -> None:
    set_setting(session, _HIDDEN_KEY, json.dumps(sorted(hidden)))


def reset_hidden(session: Session) -> None:
    delete_setting(session, _HIDDEN_KEY)


def format_count(count: int) -> str:
    return f"{count:,}".replace(",", ".")


def source_label(source: str | None) -> str:
    if source is None:
        return _UNKNOWN
    profile = PROFILES.get(source)
    return profile.label if profile is not None else source


def _completeness_chart(total: int, filled: Sequence[tuple[str, int]]) -> None:
    with ui.column().classes("gap-1"):
        ui.label("Field completeness").classes(_TITLE_CLASSES)
        ui.echart(
            {
                "grid": {"left": 8, "right": 24, "top": 8, "bottom": 8},
                "xAxis": {
                    "type": "value",
                    "max": 100,
                    "axisLabel": {"formatter": "{value}%"},
                },
                "yAxis": {
                    "type": "category",
                    "inverse": True,
                    "data": [name for name, _ in filled],
                },
                "tooltip": {
                    "trigger": "item",
                    ":formatter": "(p) => `${p.name}: ${p.data.count} / "
                    + f"{format_count(total)}`",
                },
                "series": [
                    {
                        "type": "bar",
                        "color": _BAR_COLOR,
                        "itemStyle": {"borderRadius": [0, 4, 4, 0]},
                        "data": [
                            {
                                "value": (
                                    round(100 * count / total, 1) if total else 0
                                ),
                                "count": format_count(count),
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
    with ui.column().classes("gap-1"):
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
                        "color": _BAR_COLOR,
                        "itemStyle": {"borderRadius": [4, 4, 0, 0]},
                        "data": [counts.get(year, 0) for year in years],
                    }
                ],
            }
        ).classes(_BOX_CLASSES)


def _label_pie(phase: str, screener: str, counts: Mapping[str, int]) -> None:
    with ui.column().classes("gap-1"):
        ui.label(f"Labels: {phase} / {screener}").classes(_TITLE_CLASSES)
        ui.echart(
            {
                "tooltip": {"trigger": "item"},
                "series": [
                    {
                        "type": "pie",
                        "radius": "60%",
                        "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                        "data": [
                            {
                                "name": value,
                                "value": counts[value],
                                "itemStyle": {"color": color},
                            }
                            for value, color in _LABEL_COLORS.items()
                            if counts.get(value)
                        ],
                    }
                ],
            }
        ).classes(_BOX_CLASSES)


def _keyword_table(prefix: str | None, counts: Sequence[tuple[str, int]]) -> None:
    with ui.column().classes("gap-1"):
        ui.label(_keyword_title(prefix)).classes(_TITLE_CLASSES)
        table = (
            ui.table(
                columns=[
                    {
                        "name": "keyword",
                        "label": "Keyword",
                        "field": "keyword",
                        "align": "left",
                    },
                    {"name": "count", "label": "Records", "field": "count"},
                ],
                rows=[
                    {"keyword": keyword, "count": format_count(count)}
                    for keyword, count in counts[:_TOP_KEYWORDS]
                ],
                pagination=0,
            )
            .props("dense flat bordered hide-bottom")
            .classes("w-96")
        )
        table.add_slot(
            "body-cell-keyword",
            '<q-td :props="props" :title="props.value"'
            ' class="ellipsis" style="max-width: 18rem">{{ props.value }}</q-td>',
        )


def render_library_overview(
    middle: Element,
    total: int,
    filled: Sequence[tuple[str, int]],
    per_year: Sequence[tuple[int | None, int]],
    label_counts: Mapping[tuple[str, str], Mapping[str, int]],
    keyword_counts: Mapping[str | None, Sequence[tuple[str, int]]],
    hidden: Collection[str],
) -> None:
    pies = {
        pair: counts
        for pair, counts in label_counts.items()
        if label_item_key(*pair) not in hidden
    }
    keyword_tables = {
        prefix: counts
        for prefix, counts in keyword_counts.items()
        if keyword_item_key(prefix) not in hidden
    }
    middle.clear()
    with middle:
        with ui.column().classes("w-full p-4 gap-4"):
            if (
                _COMPLETENESS in hidden
                and _PER_YEAR in hidden
                and not (pies or keyword_tables)
            ):
                ui.label(
                    "Everything is hidden. Use the gear next to Overview to choose"
                    " what's shown."
                ).classes("text-sm text-grey-6")
            with ui.row().classes("gap-6 items-start"):
                if _COMPLETENESS not in hidden:
                    _completeness_chart(total, filled)
                if _PER_YEAR not in hidden:
                    _year_chart(per_year)
                for (phase, screener), counts in pies.items():
                    _label_pie(phase, screener, counts)
                for prefix, keyword_rows in keyword_tables.items():
                    _keyword_table(prefix, keyword_rows)


def render_overview_settings(
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
        with ui.column().classes("w-full p-4 gap-2"):
            ui.label("Overview settings").classes("text-lg")
            ui.label("Shown").classes("text-sm text-grey-7")
            with ui.column().classes("gap-0"):
                for key, label in items:
                    ui.checkbox(
                        label,
                        value=key not in hidden_now,
                        on_change=lambda e, key=key: toggle(key, e.value),
                    ).props("dense")
            with ui.row().classes("gap-2 pt-2"):
                ui.button("Restore defaults", color=None, on_click=on_restore).classes(
                    "text-sm"
                ).props("dense")
                ui.button("Back to overview", color=None, on_click=on_back).classes(
                    "text-sm"
                ).props("dense")
