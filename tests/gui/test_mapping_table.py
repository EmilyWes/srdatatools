import pytest
from nicegui.elements.label import Label
from nicegui.elements.tooltip import Tooltip

from app.gui.layout import shell
from app.gui.mapping_table import (
    MappingScreen,
    _input_width_ch,
    render_mapping_table,
)
from app.models.record import Record
from app.parsers.common import FileSummary
from app.parsers.csv_ import parse_csv_record, suggest_mapping
from app.parsers.mapping import FieldMapping
from app.parsers.ris import parse_ris_record, suggest_ris_mapping


def _summary(samples: dict[str, str]) -> FileSummary:
    return FileSummary(samples, dict.fromkeys(samples, 0), 0)


def _no_preview(mapping: FieldMapping) -> Record:
    return Record()


def _render_samples(samples: dict[str, str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(samples),
        suggest_mapping(list(samples)),
        show_delimiter=True,
        preview=lambda mapping: parse_csv_record(samples, mapping).record,
    )


def _render_ris_samples(samples: dict[str, str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(samples),
        suggest_ris_mapping(list(samples)),
        show_delimiter=False,
        preview=lambda mapping: parse_ris_record(list(samples.items()), mapping).record,
    )


def _result(screen: MappingScreen, header: str) -> str:
    text: str = screen._row_for(header).result.text
    return text


def _render(headers: list[str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(dict.fromkeys(headers, "")),
        suggest_mapping(headers),
        show_delimiter=True,
        preview=_no_preview,
    )


def _render_ris(tags: list[str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(dict.fromkeys(tags, "")),
        suggest_ris_mapping(tags),
        show_delimiter=False,
        preview=_no_preview,
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
        _summary(dict.fromkeys(headers, "")),
        suggest_mapping(headers),
        show_delimiter=True,
        preview=_no_preview,
    )

    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input


def test_render_mapping_table__ris_has_no_delimiter_input_and_keeps_newline() -> None:
    panes = shell()
    tags = ["TI", "AU"]

    render_mapping_table(
        panes.middle,
        _summary(dict.fromkeys(tags, "")),
        suggest_ris_mapping(tags),
        show_delimiter=False,
        preview=_no_preview,
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
        panes.middle,
        _summary(samples),
        suggest_mapping(list(samples)),
        show_delimiter=True,
        preview=_no_preview,
    )

    assert screen._row_for("Title").sample.text == "Some Paper"
    assert screen._row_for("DOI").sample.text == "10.1/xyz"


def test_render_mapping_table__sample_has_full_value_tooltip_only_when_non_empty() -> (
    None
):
    samples = {"Title": "Some Paper", "Notes": ""}
    panes = shell()

    screen = render_mapping_table(
        panes.middle,
        _summary(samples),
        suggest_mapping(list(samples)),
        show_delimiter=True,
        preview=_no_preview,
    )

    targets = {
        tooltip.props["target"]: tooltip.text
        for tooltip in panes.middle.descendants()
        if isinstance(tooltip, Tooltip)
    }
    title_sample = screen._row_for("Title").sample
    notes_sample = screen._row_for("Notes").sample
    assert targets[f"#{title_sample.html_id}"] == "Some Paper"
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
        (["A very long column header that exceeds the cap"], 24),
    ],
)
def test_input_width_ch__fits_longest_header_within_bounds(
    headers: list[str], expected: int
) -> None:
    assert _input_width_ch(headers) == expected


def test_render_mapping_table__dropdown_options_are_sorted_alphabetically() -> None:
    screen = _render(["Title", "Year"])

    options = screen._row_for("Title").select.options
    assert isinstance(options, dict)
    labels = list(options.values())

    assert labels == sorted(labels, key=str.lower)
    assert "Ignore" in labels
    assert "Date (full)" in labels


def test_render_mapping_table__truncated_input_header_has_full_value_tooltip() -> None:
    long_header = "A very long column header that exceeds the cap"
    panes = shell()

    render_mapping_table(
        panes.middle,
        _summary({long_header: "", "Title": ""}),
        suggest_mapping([long_header, "Title"]),
        show_delimiter=True,
        preview=_no_preview,
    )

    tooltips = [t.text for t in panes.middle.descendants() if isinstance(t, Tooltip)]
    assert tooltips.count(long_header) == 1
    assert "Title" not in tooltips


def test_render_mapping_table__shows_filled_bar_per_row_with_count_tooltip() -> None:
    samples = {"Title": "Some Paper", "Notes": "", "Year": "2020"}
    summary = FileSummary(samples, {"Title": 12, "Notes": 0, "Year": 6}, 12)
    panes = shell()

    screen = render_mapping_table(
        panes.middle,
        summary,
        suggest_mapping(list(samples)),
        show_delimiter=True,
        preview=_no_preview,
    )

    title, notes, year = (screen._row_for(h).count for h in samples)
    assert (title.value, notes.value, year.value) == (1.0, 0.0, 0.5)
    tooltips = {
        c.props["target"]: c.text
        for c in panes.middle.descendants()
        if isinstance(c, Tooltip)
    }
    assert tooltips[f"#{title.html_id}"] == "12 of 12"
    assert tooltips[f"#{notes.html_id}"] == "0 of 12"
    header_texts = [e.text for e in panes.middle.descendants() if isinstance(e, Label)]
    assert "#" in header_texts


@pytest.mark.parametrize(
    ("filled", "color"),
    [(12, "green"), (8, "green"), (7, "orange"), (4, "orange"), (3, "red"), (0, "red")],
)
def test_render_mapping_table__filled_bar_color_by_thirds(
    filled: int, color: str
) -> None:
    summary = FileSummary({"Title": "Some Paper"}, {"Title": filled}, 12)
    panes = shell()

    screen = render_mapping_table(
        panes.middle,
        summary,
        suggest_mapping(["Title"]),
        show_delimiter=True,
        preview=_no_preview,
    )

    assert screen._row_for("Title").count.props["color"] == color


def test_render_mapping_table__empty_file_bar_is_empty() -> None:
    summary = FileSummary({"Title": ""}, {"Title": 0}, 0)
    panes = shell()

    screen = render_mapping_table(
        panes.middle,
        summary,
        suggest_mapping(["Title"]),
        show_delimiter=True,
        preview=_no_preview,
    )

    assert screen._row_for("Title").count.value == 0.0


def test_render_mapping_table__result_shows_parsed_scalar() -> None:
    screen = _render_samples({"Title": "Some Paper", "DOI": "https://doi.org/10.1/XYZ"})

    assert _result(screen, "Title") == "Some Paper"
    assert _result(screen, "DOI") == "10.1/xyz"


def test_render_mapping_table__result_updates_when_target_changes() -> None:
    screen = _render_samples({"Title": "Some Paper"})

    screen._row_for("Title").select.value = "notes"

    assert _result(screen, "Title") == "Some Paper"
    screen._row_for("Title").select.value = "year"
    assert _result(screen, "Title") == "not parsed"


def test_render_mapping_table__result_is_blank_for_ignored_and_empty_rows() -> None:
    screen = _render_samples({"Zzzqqqxx123": "something", "Title": ""})

    assert _result(screen, "Zzzqqqxx123") == ""
    assert _result(screen, "Title") == ""


def test_render_mapping_table__result_combines_page_start_and_end() -> None:
    screen = _render_samples({"Page start": "12", "Page end": "15"})

    assert _result(screen, "Page start") == "12-15"
    assert _result(screen, "Page end") == "12-15"


def test_render_mapping_table__result_combines_date_and_year() -> None:
    screen = _render_samples({"Date": "2020-03-15", "Year": "2021"})

    assert _result(screen, "Date") == "2021-03-15"
    assert _result(screen, "Year") == "2021-03-15"


def test_render_mapping_table__unparseable_result_is_red_not_parsed() -> None:
    screen = _render_samples({"Date": "sometime"})

    result = screen._row_for("Date").result
    assert result.text == "not parsed"
    assert "text-negative" in result.classes


def _result_color(screen: MappingScreen, header: str) -> list[str]:
    return [
        c
        for c in screen._row_for(header).result.classes
        if c in ("text-grey-7", "text-positive", "text-negative")
    ]


def test_render_mapping_table__unchanged_result_is_grey() -> None:
    screen = _render_samples({"Title": "Some Paper"})

    assert _result_color(screen, "Title") == ["text-grey-7"]


def test_render_mapping_table__changed_result_is_green() -> None:
    screen = _render_samples({"DOI": "10.1/XYZ", "Page start": "12", "Page end": "15"})

    assert _result_color(screen, "DOI") == ["text-positive"]
    assert _result_color(screen, "Page start") == ["text-positive"]


def test_render_mapping_table__blank_result_is_grey() -> None:
    screen = _render_samples({"Zzzqqqxx123": "something", "Title": ""})

    assert _result_color(screen, "Zzzqqqxx123") == ["text-grey-7"]
    assert _result_color(screen, "Title") == ["text-grey-7"]


def test_render_mapping_table__result_color_updates_when_target_changes() -> None:
    screen = _render_samples({"Title": "Some Paper"})

    screen._row_for("Title").select.value = "year"

    assert _result_color(screen, "Title") == ["text-negative"]


def test_render_mapping_table__result_splits_list_with_delimiter_input() -> None:
    screen = _render_samples({"Authors": "Smith, J; Doe, J"})
    assert _result(screen, "Authors") == "Smith, J | Doe, J"

    assert screen.list_delimiter_input is not None
    screen.list_delimiter_input.value = ","

    assert _result(screen, "Authors") == "Smith | J; Doe | J"


def test_render_mapping_table__result_labels_issn_and_isbn() -> None:
    screen = _render_ris_samples({"SN": "1234-5678; 978-3-16-148410-0"})

    assert _result(screen, "SN") == "ISSN 1234-5678 | ISBN 978-3-16-148410-0"


def _result_tooltips(screen: MappingScreen, header: str) -> list[str]:
    result = screen._row_for(header).result
    return [t.text for t in result.descendants() if isinstance(t, Tooltip)]


def test_render_mapping_table__result_has_full_value_tooltip_only_when_non_empty() -> (
    None
):
    screen = _render_samples({"Title": "Some Paper", "Notes": ""})

    assert _result_tooltips(screen, "Title") == ["Some Paper"]
    assert _result_tooltips(screen, "Notes") == []


def test_render_mapping_table__result_tooltip_is_replaced_on_refresh() -> None:
    screen = _render_samples({"Title": "Some Paper"})

    screen._row_for("Title").select.value = "year"
    assert _result_tooltips(screen, "Title") == []
    screen._row_for("Title").select.value = "notes"
    assert _result_tooltips(screen, "Title") == ["Some Paper"]


def _render_chosen(headers: list[str], chosen: FieldMapping) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(dict.fromkeys(headers, "")),
        suggest_mapping(headers),
        show_delimiter=True,
        preview=_no_preview,
        chosen=chosen,
    )


def test_render_mapping_table__chosen_mapping_overrides_suggestion() -> None:
    chosen = FieldMapping(targets={"Title": "title", "DOI": "pmid"})

    screen = _render_chosen(["Title", "DOI", "Zzzqqqxx123"], chosen)

    assert screen._row_for("DOI").select.value == "pmid"
    assert screen._row_for("Zzzqqqxx123").select.value == "ignore"
    assert _mapping_color(screen, "Title") == "green-2"
    assert _mapping_color(screen, "DOI") == "blue-2"
    assert screen.current_mapping().targets == chosen.targets


def test_render_mapping_table__chosen_other_id_keeps_key() -> None:
    chosen = FieldMapping(targets={"PMCID": "other_ids.pmcid"})

    screen = _render_chosen(["PMCID"], chosen)

    assert screen.current_mapping().targets == chosen.targets


def test_render_mapping_table__chosen_mapping_is_readonly() -> None:
    screen = _render_chosen(["Title"], FieldMapping(targets={"Title": "title"}))

    assert "readonly" in screen._row_for("Title").select.props
    assert screen.list_delimiter_input is not None
    assert "readonly" in screen.list_delimiter_input.props


def test_render_mapping_table__chosen_mapping_sets_delimiter() -> None:
    chosen = FieldMapping(targets={"Title": "title"}, list_delimiter="|")

    screen = _render_chosen(["Title"], chosen)

    assert screen.current_mapping().list_delimiter == "|"
