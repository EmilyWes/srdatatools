import json
from collections.abc import Callable, Collection, Sequence
from typing import Any

from nicegui import ui
from nicegui.element import Element
from sqlalchemy.orm import Session

from app.db.settings import delete_setting, get_setting, set_setting
from app.parsers.profiles import PROFILES

_UNKNOWN = "Unknown"
_SECTIONS_KEY = "overview_sections"

SECTIONS: dict[str, str] = {
    "total": "Total records",
    "per_source": "Records per source",
    "per_file": "Records per file",
    "per_year": "Records per year",
}
DEFAULT_SECTIONS = list(SECTIONS)


def _in_display_order(sections: Collection[str]) -> list[str]:
    return [key for key in SECTIONS if key in sections]


def load_sections(session: Session) -> list[str]:
    stored = get_setting(session, _SECTIONS_KEY)
    return (
        _in_display_order(json.loads(stored))
        if stored is not None
        else DEFAULT_SECTIONS
    )


def save_sections(session: Session, sections: Sequence[str]) -> None:
    set_setting(session, _SECTIONS_KEY, json.dumps(_in_display_order(sections)))


def reset_sections(session: Session) -> None:
    delete_setting(session, _SECTIONS_KEY)


def format_count(count: int) -> str:
    return f"{count:,}".replace(",", ".")


def source_label(source: str | None) -> str:
    if source is None:
        return _UNKNOWN
    profile = PROFILES.get(source)
    return profile.label if profile is not None else source


def _count_table(title: str, heading: str, rows: list[tuple[str, int]]) -> None:
    with ui.column().classes("gap-1"):
        ui.label(title).classes("text-sm text-grey-7")
        ui.table(
            columns=[
                {"name": "name", "label": heading, "field": "name", "align": "left"},
                {"name": "count", "label": "Records", "field": "count"},
            ],
            rows=[{"name": name, "count": format_count(count)} for name, count in rows],
            pagination=0,
        ).props("dense flat bordered hide-bottom").classes("min-w-48")


def render_library_overview(
    middle: Element,
    total: int,
    per_source: Sequence[tuple[str | None, int]],
    per_file: Sequence[tuple[str, int]],
    per_year: Sequence[tuple[int | None, int]],
    sections: Collection[str],
) -> None:
    middle.clear()
    with middle:
        with ui.column().classes("w-full p-4 gap-4"):
            if not sections:
                ui.label(
                    "No sections selected. Use the gear next to Overview to choose"
                    " what's shown."
                ).classes("text-sm text-grey-6")
            if "total" in sections:
                with ui.column().classes("gap-0"):
                    ui.label(SECTIONS["total"]).classes("text-sm text-grey-7")
                    ui.label(format_count(total)).classes("text-3xl")
            with ui.row().classes("gap-6 items-start"):
                if "per_source" in sections:
                    _count_table(
                        SECTIONS["per_source"],
                        "Source",
                        [(source_label(source), count) for source, count in per_source],
                    )
                if "per_file" in sections:
                    _count_table(SECTIONS["per_file"], "File", list(per_file))
                if "per_year" in sections:
                    _count_table(
                        SECTIONS["per_year"],
                        "Year",
                        [
                            (str(year) if year is not None else _UNKNOWN, count)
                            for year, count in per_year
                        ],
                    )


def render_overview_settings(
    middle: Element,
    sections: Sequence[str],
    on_change: Callable[[list[str]], Any],
    on_restore: Callable[[], Any],
    on_back: Callable[[], Any],
) -> None:
    selected = set(sections)

    def toggle(key: str, checked: bool) -> None:
        if checked:
            selected.add(key)
        else:
            selected.discard(key)
        on_change(_in_display_order(selected))

    middle.clear()
    with middle:
        with ui.column().classes("w-full p-4 gap-2"):
            ui.label("Overview settings").classes("text-lg")
            ui.label("Sections").classes("text-sm text-grey-7")
            with ui.column().classes("gap-0"):
                for key, label in SECTIONS.items():
                    ui.checkbox(
                        label,
                        value=key in selected,
                        on_change=lambda e, key=key: toggle(key, e.value),
                    ).props("dense")
            with ui.row().classes("gap-2 pt-2"):
                ui.button("Restore defaults", color=None, on_click=on_restore).classes(
                    "text-sm"
                ).props("dense")
                ui.button("Back to overview", color=None, on_click=on_back).classes(
                    "text-sm"
                ).props("dense")
