from collections.abc import Sequence

from nicegui import ui
from nicegui.element import Element

from app.parsers.profiles import PROFILES

_UNKNOWN = "Unknown"


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
            rows=[{"name": name, "count": count} for name, count in rows],
            pagination=0,
        ).props("dense flat bordered hide-bottom").classes("min-w-48")


def render_library_overview(
    middle: Element,
    total: int,
    per_source: Sequence[tuple[str | None, int]],
    per_file: Sequence[tuple[str, int]],
    per_year: Sequence[tuple[int | None, int]],
) -> None:
    middle.clear()
    with middle:
        with ui.column().classes("w-full p-4 gap-4"):
            with ui.column().classes("gap-0"):
                ui.label("Total records").classes("text-sm text-grey-7")
                ui.label(str(total)).classes("text-3xl")
            with ui.row().classes("gap-6 items-start"):
                _count_table(
                    "Records per source",
                    "Source",
                    [(source_label(source), count) for source, count in per_source],
                )
                _count_table("Records per file", "File", list(per_file))
                _count_table(
                    "Records per year",
                    "Year",
                    [
                        (str(year) if year is not None else _UNKNOWN, count)
                        for year, count in per_year
                    ],
                )
