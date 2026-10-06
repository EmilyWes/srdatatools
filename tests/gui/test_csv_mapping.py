from app.gui.csv_mapping import CsvMappingScreen, render_csv_mapping
from app.gui.layout import shell


def _render(headers: list[str]) -> CsvMappingScreen:
    panes = shell()
    return render_csv_mapping(panes.middle, headers)


def test_render_csv_mapping__prefills_suggested_scalar_targets() -> None:
    screen = _render(["Title", "DOI"])

    assert screen._row_for("Title").select.value == "title"
    assert screen._row_for("DOI").select.value == "doi"


def test_render_csv_mapping__unrecognized_header_defaults_to_ignore() -> None:
    screen = _render(["Zzzqqqxx123"])

    assert screen._row_for("Zzzqqqxx123").select.value == "ignore"


def test_render_csv_mapping__current_mapping_with_scalar_fields() -> None:
    screen = _render(["Title", "DOI", "Zzzqqqxx123"])

    assert screen.current_mapping().targets == {"Title": "title", "DOI": "doi"}


def test_render_csv_mapping__combines_two_columns_mapped_to_authors() -> None:
    screen = _render(["First Author", "Other Authors"])

    screen.set_target("First Author", "authors")
    screen.set_target("Other Authors", "authors")

    assert screen.current_mapping().targets == {
        "First Author": "authors",
        "Other Authors": "authors",
    }


def test_render_csv_mapping__combines_two_columns_mapped_to_keywords() -> None:
    screen = _render(["Author Keywords", "Index Keywords"])

    screen.set_target("Author Keywords", "keywords")
    screen.set_target("Index Keywords", "keywords")

    assert screen.current_mapping().targets == {
        "Author Keywords": "keywords",
        "Index Keywords": "keywords",
    }


def test_render_csv_mapping__other_id_key_defaults_to_slug_and_is_editable() -> None:
    screen = _render(["Scopus Author ID"])

    screen.set_target("Scopus Author ID", "other_ids")
    assert screen._row_for("Scopus Author ID").key_input.value == "scopus_author_id"

    screen.set_other_id_key("Scopus Author ID", "custom_key")

    assert screen.current_mapping().targets == {
        "Scopus Author ID": "other_ids.custom_key"
    }


def test_render_csv_mapping__prefills_suggested_other_id_with_key() -> None:
    screen = _render(["PMCID"])

    row = screen._row_for("PMCID")
    assert row.select.value == "other_ids"
    assert row.key_input.value == "pmcid"
    assert screen.current_mapping().targets == {"PMCID": "other_ids.pmcid"}


def test_render_csv_mapping__picking_year_removes_year_from_other_rows() -> None:
    screen = _render(["Year", "Publication Year"])

    screen.set_target("Year", "year")

    assert "year" not in screen.available_targets("Publication Year")
    assert "year" in screen.available_targets("Year")


def test_render_csv_mapping__date_and_year_can_be_mapped_together() -> None:
    screen = _render(["Publication Year", "Publication Date"])

    assert screen._row_for("Publication Year").select.value == "year"
    assert screen._row_for("Publication Date").select.value == "date"
    assert "date" in screen.available_targets("Publication Date")
    assert "year" in screen.available_targets("Publication Year")

    assert screen.current_mapping().targets == {
        "Publication Year": "year",
        "Publication Date": "date",
    }


def test_render_csv_mapping__conflicting_suggested_years_only_keeps_first() -> None:
    screen = _render(["Year", "Publication Year"])

    assert screen._row_for("Year").select.value == "year"
    assert screen._row_for("Publication Year").select.value == "ignore"


def test_render_csv_mapping__renders_table_and_delimiter_input_only() -> None:
    panes = shell()

    render_csv_mapping(panes.middle, ["Title"])

    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input
