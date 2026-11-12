import pytest
from nicegui import ui
from nicegui.elements.label import Label
from nicegui.elements.tooltip import Tooltip

from app.gui.layout import shell
from app.gui.mapping_table import (
    MappingScreen,
    _input_width_ch,
    render_mapping_table,
)
from app.parsers.common import FileSummary
from app.parsers.csv_ import suggest_mapping
from app.parsers.mapping import (
    AuthorsRow,
    DateRow,
    FieldMapping,
    LabelRow,
    OtherIdRow,
    PagesRow,
    ScalarRow,
    Suggest,
)
from app.parsers.ris import suggest_ris_mapping
from tests.mappings import mapping_of, targets_of


def _summary(samples: dict[str, str]) -> FileSummary:
    return FileSummary(samples, dict.fromkeys(samples, 0), 0)


def _render_samples(samples: dict[str, str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(samples),
        suggest_mapping(list(samples)),
    )


def _render_ris_samples(samples: dict[str, str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(samples),
        suggest_ris_mapping(list(samples)),
    )


def _render(headers: list[str]) -> MappingScreen:
    return _render_samples(dict.fromkeys(headers, ""))


def _render_ris(tags: list[str]) -> MappingScreen:
    return _render_ris_samples(dict.fromkeys(tags, ""))


def _visible_options(screen: MappingScreen, header: str) -> list[str]:
    option_rows = screen._row_for(header).option_rows
    return [name for name, option_row in option_rows.items() if option_row.visible]


def _input(screen: MappingScreen, header: str, name: str) -> ui.input:
    widget = screen._row_for(header).inputs[name]
    assert isinstance(widget, ui.input)
    return widget


def test_render_mapping_table__prefills_suggested_scalar_targets() -> None:
    screen = _render(["Title", "DOI"])

    assert screen._row_for("Title").select.value == "title"
    assert screen._row_for("DOI").select.value == "doi"


def test_render_mapping_table__ris_sn_prefills_issn_isbn_option() -> None:
    screen = _render_ris(["SN"])

    assert screen._row_for("SN").select.value == "issn_isbn"
    assert targets_of(screen.current_mapping()) == {"SN": "issn_isbn"}


def test_render_mapping_table__unrecognized_header_defaults_to_ignore() -> None:
    screen = _render(["Zzzqqqxx123"])

    assert screen._row_for("Zzzqqqxx123").select.value == "ignore"


def test_render_mapping_table__current_mapping_with_scalar_fields() -> None:
    screen = _render(["Title", "DOI", "Zzzqqqxx123"])

    assert screen.current_mapping().rows == {
        "Title": ScalarRow(target="title"),
        "DOI": ScalarRow(target="doi"),
    }


def test_render_mapping_table__several_rows_may_share_any_target() -> None:
    screen = _render(["Year", "Publication Year", "Start", "Other"])

    screen.set_target("Start", "pages")
    screen.set_target("Other", "pages")

    assert targets_of(screen.current_mapping()) == {
        "Year": "date",
        "Publication Year": "date",
        "Start": "pages",
        "Other": "pages",
    }


def test_render_mapping_table__dropdown_has_one_entry_per_target() -> None:
    options = _render(["Title"])._row_for("Title").select.options
    assert isinstance(options, dict)

    assert {"date", "pages", "issn_isbn", "other_ids", "authors"} <= set(options)
    assert not {"year", "page_start", "issn", "isbn"} & set(options)


def test_render_mapping_table__dropdown_options_are_sorted_alphabetically() -> None:
    options = _render(["Title"])._row_for("Title").select.options
    assert isinstance(options, dict)
    labels = list(options.values())

    assert labels == sorted(labels, key=str.lower)
    assert "Ignore" in labels
    assert "Publication date" in labels
    assert options["label"] == "Label"


def test_render_mapping_table__renders_only_the_table() -> None:
    panes = shell()

    render_mapping_table(
        panes.middle,
        _summary({"Title": ""}),
        suggest_mapping(["Title"]),
    )

    assert len(panes.middle.default_slot.children) == 1


def test_render_mapping_table__prefills_suggested_options() -> None:
    screen = _render(["Year", "Page start", "PMCID"])

    assert screen._row_for("Year").inputs["part"].value == "year"
    assert screen._row_for("Page start").inputs["part"].value == "start"
    assert _input(screen, "PMCID", "key").props["placeholder"] == "pmcid"
    assert screen.current_mapping().rows == {
        "Year": DateRow(part="year"),
        "Page start": PagesRow(part="start"),
        "PMCID": OtherIdRow(key="pmcid"),
    }


def test_render_mapping_table__scalar_and_ignored_rows_have_no_options() -> None:
    screen = _render(["Title", "Zzzqqqxx123"])

    assert screen._row_for("Title").inputs == {}
    assert screen._row_for("Zzzqqqxx123").inputs == {}


def test_render_mapping_table__picking_a_target_shows_its_default_options() -> None:
    screen = _render(["Scopus Author ID"])

    screen.set_target("Scopus Author ID", "authors")

    assert screen._row_for("Scopus Author ID").inputs["role"].value == "names"
    assert screen.current_mapping().rows == {
        "Scopus Author ID": AuthorsRow(id_key="scopus_author_id")
    }


def test_render_mapping_table__other_id_key_defaults_to_slug_and_is_editable() -> None:
    screen = _render(["Scopus Author ID"])
    screen.set_target("Scopus Author ID", "other_ids")

    assert screen.current_mapping().rows == {
        "Scopus Author ID": OtherIdRow(key="scopus_author_id")
    }
    screen.set_option("Scopus Author ID", "key", " scopus ")
    assert screen.current_mapping().rows == {
        "Scopus Author ID": OtherIdRow(key="scopus")
    }


def test_render_mapping_table__empty_text_box_uses_placeholder() -> None:
    screen = _render(["included"])

    screen.set_option("included", "phase", "tiab")
    screen.set_option("included", "phase", "")

    assert screen.current_mapping().rows == {"included": LabelRow()}


def test_render_mapping_table__typed_prefix_loses_brackets_and_spaces() -> None:
    screen = _render_samples({"Keywords": "a; b"})

    screen.set_option("Keywords", "prefix", " [Author] ")

    assert screen.current_mapping().rows["Keywords"].model_dump()["prefix"] == "Author"


def test_render_mapping_table__date_rows_only_show_part() -> None:
    screen = _render(["Date", "Year"])

    assert _visible_options(screen, "Date") == ["part"]
    assert _visible_options(screen, "Year") == ["part"]


def test_render_mapping_table__only_author_ids_show_id_key() -> None:
    screen = _render(["Authors"])

    assert _visible_options(screen, "Authors") == ["role"]
    screen.set_option("Authors", "role", "ids")
    assert _visible_options(screen, "Authors") == ["role", "id_key"]
    screen.set_option("Authors", "role", "affiliations")
    assert _visible_options(screen, "Authors") == ["role"]


def test_render_mapping_table__switching_target_back_restores_suggested_options() -> (
    None
):
    screen = _render(["Year"])

    screen.set_target("Year", "notes")
    screen.set_target("Year", "date")

    assert screen.current_mapping().rows == {"Year": DateRow(part="year")}


def test_render_mapping_table__options_have_short_labels_with_full_tooltips() -> None:
    screen = _render(["Authors"])
    option_rows = screen._row_for("Authors").option_rows

    labels = {
        name: next(e for e in option_row.descendants() if isinstance(e, Label))
        for name, option_row in option_rows.items()
    }
    tooltips = {
        name: [
            t.text
            for t in label.client.layout.descendants()
            if isinstance(t, Tooltip) and t.props.get("target") == f"#{label.html_id}"
        ]
        for name, label in labels.items()
    }
    assert {name: label.text for name, label in labels.items()} == {
        "role": "role:",
        "id_key": "key:",
    }
    assert tooltips == {
        "role": ["Role"],
        "id_key": ["ID key"],
    }


def test_render_mapping_table__shows_sample_value_for_each_row() -> None:
    screen = _render_samples({"Title": "Some Paper", "DOI": "10.1/xyz"})

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


def test_render_mapping_table__truncated_input_header_has_full_value_tooltip() -> None:
    long_header = "A very long column header that exceeds the cap"
    panes = shell()

    render_mapping_table(
        panes.middle,
        _summary({long_header: "", "Title": ""}),
        suggest_mapping([long_header, "Title"]),
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
    )

    assert screen._row_for("Title").count.props["color"] == color


def test_render_mapping_table__empty_file_bar_is_empty() -> None:
    summary = FileSummary({"Title": ""}, {"Title": 0}, 0)
    panes = shell()

    screen = render_mapping_table(
        panes.middle,
        summary,
        suggest_mapping(["Title"]),
    )

    assert screen._row_for("Title").count.value == 0.0


def _render_chosen(headers: list[str], chosen: FieldMapping) -> MappingScreen:
    samples = dict.fromkeys(headers, "")
    panes = shell()
    return render_mapping_table(
        panes.middle,
        _summary(samples),
        suggest_mapping(headers),
        chosen=chosen,
    )


def test_render_mapping_table__chosen_mapping_overrides_suggestion() -> None:
    chosen = mapping_of({"Title": "title", "DOI": "pmid"})

    screen = _render_chosen(["Title", "DOI", "Zzzqqqxx123"], chosen)

    assert screen._row_for("DOI").select.value == "pmid"
    assert screen._row_for("Zzzqqqxx123").select.value == "ignore"
    assert _mapping_color(screen, "Title") == "green-2"
    assert _mapping_color(screen, "DOI") == "blue-2"
    assert screen.current_mapping() == chosen


def test_render_mapping_table__chosen_options_are_kept() -> None:
    chosen = mapping_of(
        {
            "PMCID": Suggest("other_ids", {"key": "pmc"}),
            "Authors": Suggest("authors", {"role": "affiliations"}),
        }
    )

    screen = _render_chosen(["PMCID", "Authors"], chosen)

    assert screen.current_mapping() == chosen


def test_render_mapping_table__chosen_mapping_is_readonly_and_shows_values() -> None:
    chosen = mapping_of(
        {
            "Date": Suggest("date", {"part": "year"}),
            "Keywords": Suggest("keywords", {"prefix": "MeSH"}),
        }
    )

    screen = _render_chosen(["Date", "Keywords"], chosen)

    assert "readonly" in screen._row_for("Date").select.props
    assert "readonly" in screen._row_for("Date").inputs["part"].props
    prefix = _input(screen, "Keywords", "prefix")
    assert "readonly" in prefix.props
    assert prefix.value == "MeSH"


def test_render_mapping_table__label_rows_show_phase_and_screener() -> None:
    screen = _render(["included", "Title"])

    assert _visible_options(screen, "included") == ["phase", "screener"]
    assert _input(screen, "included", "phase").props["placeholder"] == "ft"
    assert _input(screen, "included", "screener").props["placeholder"] == "screener 1"


def test_render_mapping_table__picking_label_shows_inputs_and_back_hides() -> None:
    screen = _render(["Title"])

    screen.set_target("Title", "label")
    assert _visible_options(screen, "Title") == ["phase", "screener"]

    screen.set_target("Title", "title")
    assert screen._row_for("Title").inputs == {}


def test_render_mapping_table__current_mapping_uses_typed_phase_and_screener() -> None:
    screen = _render(["included"])
    screen.set_option("included", "phase", "tiab")
    screen.set_option("included", "screener", "Emily")

    assert screen.current_mapping().rows == {
        "included": LabelRow(phase="tiab", screener="Emily")
    }


def test_render_mapping_table__empty_label_inputs_fall_back_to_placeholders() -> None:
    screen = _render(["included"])
    screen.set_option("included", "phase", "  ")

    assert screen.current_mapping().rows == {
        "included": LabelRow(phase="ft", screener="screener 1")
    }


def test_render_mapping_table__chosen_label_prefills_readonly_inputs() -> None:
    chosen = mapping_of(
        {"included": Suggest("label", {"phase": "tiab", "screener": "Emily"})}
    )

    screen = _render_chosen(["included"], chosen)

    phase, screener = (_input(screen, "included", n) for n in ("phase", "screener"))
    assert (phase.value, screener.value) == ("tiab", "Emily")
    assert "readonly" in phase.props
    assert "readonly" in screener.props


def _option_color(screen: MappingScreen, header: str, name: str) -> str:
    return str(screen._row_for(header).inputs[name].props["bg-color"])


def test_render_mapping_table__options_fitting_the_example_are_green() -> None:
    screen = _render_samples({"Authors": "Smith, J; Doe, J", "Year": "2020"})

    assert _option_color(screen, "Authors", "role") == "green-2"
    assert _option_color(screen, "Year", "part") == "green-2"


def test_render_mapping_table__changed_option_turns_blue_and_back() -> None:
    screen = _render_samples({"Authors": "Smith, J; Doe, J"})

    screen.set_option("Authors", "role", "affiliations")
    assert _option_color(screen, "Authors", "role") == "blue-2"

    screen.set_option("Authors", "role", "names")
    assert _option_color(screen, "Authors", "role") == "green-2"


def test_render_mapping_table__typing_the_placeholder_is_not_a_change() -> None:
    screen = _render_samples({"included": "yes"})

    screen.set_option("included", "phase", "ft")

    assert _option_color(screen, "included", "phase") == "green-2"
