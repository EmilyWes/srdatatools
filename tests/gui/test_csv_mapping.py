from app.gui.csv_mapping import CsvMappingScreen, render_csv_mapping
from app.gui.layout import shell
from app.parsers.csv_ import ColumnMapping


def _render(headers: list[str]) -> tuple[list[ColumnMapping], CsvMappingScreen]:
    panes = shell()
    confirmed: list[ColumnMapping] = []
    screen = render_csv_mapping(panes.middle, headers, confirmed.append)
    return confirmed, screen


def test_render_csv_mapping__prefills_suggested_scalar_targets() -> None:
    _, screen = _render(["Title", "DOI"])

    assert screen._row_for("Title").select.value == "title"
    assert screen._row_for("DOI").select.value == "doi"


def test_render_csv_mapping__unrecognized_header_defaults_to_ignore() -> None:
    _, screen = _render(["Zzzqqqxx123"])

    assert screen._row_for("Zzzqqqxx123").select.value == "ignore"


def test_render_csv_mapping__confirm_with_scalar_fields_builds_mapping() -> None:
    confirmed, screen = _render(["Title", "DOI", "Zzzqqqxx123"])

    screen.confirm()

    assert len(confirmed) == 1
    assert confirmed[0].fields == {"Title": "title", "DOI": "doi"}


def test_render_csv_mapping__combines_two_columns_mapped_to_authors() -> None:
    confirmed, screen = _render(["First Author", "Other Authors"])

    screen.set_target("First Author", "authors")
    screen.set_target("Other Authors", "authors")
    screen.confirm()

    assert confirmed[0].authors_columns == ["First Author", "Other Authors"]


def test_render_csv_mapping__combines_two_columns_mapped_to_keywords() -> None:
    confirmed, screen = _render(["Author Keywords", "Index Keywords"])

    screen.set_target("Author Keywords", "keywords")
    screen.set_target("Index Keywords", "keywords")
    screen.confirm()

    assert confirmed[0].keywords_columns == ["Author Keywords", "Index Keywords"]


def test_render_csv_mapping__other_id_key_defaults_to_slug_and_is_editable() -> None:
    confirmed, screen = _render(["Scopus Author ID"])

    screen.set_target("Scopus Author ID", "other_id")
    assert screen._row_for("Scopus Author ID").key_input.value == "scopus_author_id"

    screen.set_other_id_key("Scopus Author ID", "custom_key")
    screen.confirm()

    assert confirmed[0].fields == {"Scopus Author ID": "other_ids.custom_key"}


def test_render_csv_mapping__picking_year_removes_year_from_other_rows() -> None:
    _, screen = _render(["Year", "Publication Year"])

    screen.set_target("Year", "year")

    assert "year" not in screen.available_targets("Publication Year")
    assert "year" in screen.available_targets("Year")


def test_render_csv_mapping__picking_date_removes_year_month_day_from_other_rows() -> (
    None
):
    _, screen = _render(["Date", "Other Column"])

    screen.set_target("Date", "date")

    assert screen.available_targets("Other Column") & {"year", "month", "day"} == set()
    # the row holding "date" may still switch itself to year/month/day
    assert {"year", "month", "day"} <= screen.available_targets("Date")


def test_render_csv_mapping__picking_year_removes_date_from_other_rows() -> None:
    _, screen = _render(["Year", "Other Column"])

    screen.set_target("Year", "year")

    assert "date" not in screen.available_targets("Other Column")
    # the row holding "year" may still switch itself to date
    assert "date" in screen.available_targets("Year")


def test_render_csv_mapping__conflicting_suggested_years_only_keeps_first() -> None:
    _, screen = _render(["Year", "Publication Year"])

    assert screen._row_for("Year").select.value == "year"
    assert screen._row_for("Publication Year").select.value == "ignore"


def test_render_csv_mapping__current_mapping_matches_confirm_callback_result() -> None:
    confirmed, screen = _render(["Title", "DOI"])

    live_mapping = screen.current_mapping()
    screen.confirm()

    assert confirmed == [live_mapping]


def test_render_csv_mapping__show_confirm_button_false_omits_button() -> None:
    panes = shell()

    render_csv_mapping(
        panes.middle, ["Title"], lambda _m: None, show_confirm_button=False
    )

    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input, no button
