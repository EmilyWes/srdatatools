import pytest
from nicegui.elements.tooltip import Tooltip

from app.gui.layout import shell
from app.gui.mapping_table import (
    MappingScreen,
    _input_width_ch,
    render_mapping_table,
)
from app.parsers.csv_ import suggest_mapping
from app.parsers.ris import suggest_ris_mapping


def _render(headers: list[str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        dict.fromkeys(headers, ""),
        suggest_mapping(headers),
        show_delimiter=True,
    )


def _render_ris(tags: list[str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        dict.fromkeys(tags, ""),
        suggest_ris_mapping(tags),
        show_delimiter=False,
    )


def test_render_mapping_table__prefills_suggested_scalar_targets() -> None:
    screen = _render(["Title", "DOI"])

    assert screen._row_for("Title").select.value == "title"
    assert screen._row_for("DOI").select.value == "doi"


def test_render_mapping_table__ris_sn_prefills_issn_isbn_option() -> None:
    screen = _render_ris(["SN"])

    assert screen._row_for("SN").select.value == "issn_isbn"
    assert "issn_isbn" in screen.available_targets("SN")
    assert screen.current_mapping().targets == {"SN": "issn_isbn"}


def test_render_mapping_table__prefills_page_start_and_end() -> None:
    screen = _render(["Page start", "Page end"])

    assert screen.current_mapping().targets == {
        "Page start": "page_start",
        "Page end": "page_end",
    }


def test_render_mapping_table__unrecognized_header_defaults_to_ignore() -> None:
    screen = _render(["Zzzqqqxx123"])

    assert screen._row_for("Zzzqqqxx123").select.value == "ignore"


def test_render_mapping_table__current_mapping_with_scalar_fields() -> None:
    screen = _render(["Title", "DOI", "Zzzqqqxx123"])

    assert screen.current_mapping().targets == {"Title": "title", "DOI": "doi"}


def test_render_mapping_table__combines_two_columns_mapped_to_authors() -> None:
    screen = _render(["First Author", "Other Authors"])

    screen.set_target("First Author", "authors")
    screen.set_target("Other Authors", "authors")

    assert screen.current_mapping().targets == {
        "First Author": "authors",
        "Other Authors": "authors",
    }


def test_render_mapping_table__combines_two_columns_mapped_to_keywords() -> None:
    screen = _render(["Author Keywords", "Index Keywords"])

    screen.set_target("Author Keywords", "keywords")
    screen.set_target("Index Keywords", "keywords")

    assert screen.current_mapping().targets == {
        "Author Keywords": "keywords",
        "Index Keywords": "keywords",
    }


def test_render_mapping_table__other_id_key_is_slug_of_header() -> None:
    screen = _render(["Scopus Author ID"])

    screen.set_target("Scopus Author ID", "other_ids")

    assert screen.current_mapping().targets == {
        "Scopus Author ID": "other_ids.scopus_author_id"
    }


def test_render_mapping_table__prefills_suggested_other_id_with_key() -> None:
    screen = _render(["PMCID"])

    assert screen._row_for("PMCID").select.value == "other_ids"
    assert screen.current_mapping().targets == {"PMCID": "other_ids.pmcid"}


def test_render_mapping_table__picking_year_removes_year_from_other_rows() -> None:
    screen = _render(["Year", "Publication Year"])

    screen.set_target("Year", "year")

    assert "year" not in screen.available_targets("Publication Year")
    assert "year" in screen.available_targets("Year")


def test_render_mapping_table__date_and_year_can_be_mapped_together() -> None:
    screen = _render(["Publication Year", "Publication Date"])

    assert screen._row_for("Publication Year").select.value == "year"
    assert screen._row_for("Publication Date").select.value == "date"
    assert "date" in screen.available_targets("Publication Date")
    assert "year" in screen.available_targets("Publication Year")

    assert screen.current_mapping().targets == {
        "Publication Year": "year",
        "Publication Date": "date",
    }


def test_render_mapping_table__conflicting_suggested_years_only_keeps_first() -> None:
    screen = _render(["Year", "Publication Year"])

    assert screen._row_for("Year").select.value == "year"
    assert screen._row_for("Publication Year").select.value == "ignore"


def test_render_mapping_table__renders_table_and_delimiter_input_only() -> None:
    panes = shell()
    headers = ["Title"]

    render_mapping_table(
        panes.middle,
        dict.fromkeys(headers, ""),
        suggest_mapping(headers),
        show_delimiter=True,
    )

    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input


def test_render_mapping_table__ris_has_no_delimiter_input_and_keeps_newline() -> None:
    panes = shell()
    tags = ["TI", "AU"]

    render_mapping_table(
        panes.middle,
        dict.fromkeys(tags, ""),
        suggest_ris_mapping(tags),
        show_delimiter=False,
    )

    assert len(panes.middle.default_slot.children) == 1  # table only


def test_render_mapping_table__ris_prefills_tags_and_uses_newline_delimiter() -> None:
    screen = _render_ris(["TI", "AU", "ZZ", "SP", "EP"])

    mapping = screen.current_mapping()

    assert mapping.targets == {
        "TI": "title",
        "AU": "authors",
        "SP": "page_start",
        "EP": "page_end",
    }
    assert mapping.list_delimiter == "\n"
    assert screen._row_for("ZZ").select.value == "ignore"


def test_render_mapping_table__picking_page_start_removes_it_from_other_rows() -> None:
    screen = _render(["Start", "Other"])

    screen.set_target("Start", "page_start")

    assert "page_start" not in screen.available_targets("Other")
    assert "page_start" in screen.available_targets("Start")


def test_render_mapping_table__shows_sample_value_for_each_row() -> None:
    samples = {"Title": "Some Paper", "DOI": "10.1/xyz"}
    panes = shell()

    screen = render_mapping_table(
        panes.middle, samples, suggest_mapping(list(samples)), show_delimiter=True
    )

    assert screen._row_for("Title").sample.text == "Some Paper"
    assert screen._row_for("DOI").sample.text == "10.1/xyz"


def test_render_mapping_table__sample_has_full_value_tooltip_only_when_non_empty() -> (
    None
):
    samples = {"Title": "Some Paper", "Notes": ""}
    panes = shell()

    screen = render_mapping_table(
        panes.middle, samples, suggest_mapping(list(samples)), show_delimiter=True
    )

    targets = {
        tooltip.props["target"]: tooltip.text
        for tooltip in panes.middle.descendants()
        if isinstance(tooltip, Tooltip)
    }
    title_sample = screen._row_for("Title").sample
    notes_sample = screen._row_for("Notes").sample
    assert targets == {f"#{title_sample.html_id}": "Some Paper"}
    assert f"#{notes_sample.html_id}" not in targets


def _statuses(screen: MappingScreen) -> list[tuple[str, str]]:
    return [(row.header, row.status) for row in screen.rows]


def test_render_mapping_table__exact_match_is_green() -> None:
    screen = _render(["DOI"])

    assert _statuses(screen) == [("DOI", "green")]


def test_render_mapping_table__fuzzy_and_id_fallback_are_orange() -> None:
    screen = _render(["Titles", "Scopus Author ID"])

    assert {status for _, status in _statuses(screen)} == {"orange"}


def test_render_mapping_table__several_keys_on_same_target_are_orange() -> None:
    screen = _render(["Author Keywords", "Index Keywords", "DOI"])

    assert dict(_statuses(screen)) == {
        "DOI": "green",
        "Author Keywords": "orange",
        "Index Keywords": "orange",
    }


def test_render_mapping_table__ignored_is_red() -> None:
    screen = _render(["Zzzqqqxx123"])

    assert _statuses(screen) == [("Zzzqqqxx123", "red")]


def test_render_mapping_table__sorts_green_then_orange_then_red() -> None:
    screen = _render(["Zzzqqqxx123", "Scopus Author ID", "DOI"])

    assert [status for _, status in _statuses(screen)] == ["green", "orange", "red"]


def test_render_mapping_table__sorts_within_status_by_field_sequence() -> None:
    screen = _render(["Notes", "Title", "Authors", "DOI"])

    assert [row.header for row in screen.rows] == ["DOI", "Title", "Authors", "Notes"]


def test_render_mapping_table__sort_keeps_file_order_for_ties() -> None:
    screen = _render(["Zzzqqqxx123", "Aaaa111", "Author Keywords", "Index Keywords"])

    assert [row.header for row in screen.rows] == [
        "Author Keywords",
        "Index Keywords",
        "Zzzqqqxx123",
        "Aaaa111",
    ]


def test_render_mapping_table__other_ids_sort_between_url_and_notes() -> None:
    screen = _render(["Notes", "PMCID", "Title"])

    assert [row.header for row in screen.rows] == ["Title", "PMCID", "Notes"]


def _mapping_color(screen: MappingScreen, header: str) -> str:
    return str(screen._row_for(header).select.props["bg-color"])


def test_render_mapping_table__mapping_cell_is_tinted_by_status() -> None:
    screen = _render(["DOI", "Titles", "Zzzqqqxx123"])

    assert _mapping_color(screen, "DOI") == "green-2"
    assert _mapping_color(screen, "Titles") == "orange-2"
    assert _mapping_color(screen, "Zzzqqqxx123") == "red-2"


def test_render_mapping_table__changed_row_turns_blue() -> None:
    screen = _render(["DOI", "Zzzqqqxx123"])

    screen.set_target("DOI", "pmid")
    screen.set_target("Zzzqqqxx123", "language")

    assert _mapping_color(screen, "DOI") == "blue-2"
    assert _mapping_color(screen, "Zzzqqqxx123") == "blue-2"


def test_render_mapping_table__reverting_change_restores_original_color() -> None:
    screen = _render(["DOI"])

    screen.set_target("DOI", "pmid")
    screen.set_target("DOI", "doi")

    assert _mapping_color(screen, "DOI") == "green-2"


def test_render_mapping_table__changing_a_row_does_not_reorder_rows() -> None:
    screen = _render(["DOI", "Title"])

    screen.set_target("DOI", "notes")

    assert [row.header for row in screen.rows] == ["DOI", "Title"]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        (["ID"], 8),
        (["Title", "Publication Year"], 17),
        (["A very long column header that exceeds the cap"], 28),
    ],
)
def test_input_width_ch__fits_longest_header_within_bounds(
    headers: list[str], expected: int
) -> None:
    assert _input_width_ch(headers) == expected
