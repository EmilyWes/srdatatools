from app.gui.layout import shell
from app.gui.mapping_table import MappingScreen, render_mapping_table
from app.parsers.csv_ import suggest_mapping
from app.parsers.ris import suggest_ris_mapping


def _render(headers: list[str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle, headers, suggest_mapping(headers), show_delimiter=True
    )


def _render_ris(tags: list[str]) -> MappingScreen:
    panes = shell()
    return render_mapping_table(
        panes.middle, tags, suggest_ris_mapping(tags), show_delimiter=False
    )


def test_render_mapping_table__prefills_suggested_scalar_targets() -> None:
    screen = _render(["Title", "DOI"])

    assert screen._row_for("Title").select.value == "title"
    assert screen._row_for("DOI").select.value == "doi"


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


def test_render_mapping_table__other_id_key_defaults_to_slug_and_is_editable() -> None:
    screen = _render(["Scopus Author ID"])

    screen.set_target("Scopus Author ID", "other_ids")
    assert screen._row_for("Scopus Author ID").key_input.value == "scopus_author_id"

    screen.set_other_id_key("Scopus Author ID", "custom_key")

    assert screen.current_mapping().targets == {
        "Scopus Author ID": "other_ids.custom_key"
    }


def test_render_mapping_table__prefills_suggested_other_id_with_key() -> None:
    screen = _render(["PMCID"])

    row = screen._row_for("PMCID")
    assert row.select.value == "other_ids"
    assert row.key_input.value == "pmcid"
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
        panes.middle, headers, suggest_mapping(headers), show_delimiter=True
    )

    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input


def test_render_mapping_table__ris_has_no_delimiter_input_and_keeps_newline() -> None:
    panes = shell()
    tags = ["TI", "AU"]

    render_mapping_table(
        panes.middle, tags, suggest_ris_mapping(tags), show_delimiter=False
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
