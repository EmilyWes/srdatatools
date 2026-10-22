import asyncio
import datetime
from pathlib import Path
from typing import Any

import pytest
from nicegui.elements.icon import Icon
from nicegui.elements.tooltip import Tooltip
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Record
from app.gui import import_flow
from app.gui.import_flow import (
    ImportView,
    import_bibtex,
    import_csv,
    import_file,
    import_nbib,
    import_ris,
    pick_file,
    render_import_view,
    render_mapping,
)
from app.gui.layout import shell
from app.gui.mapping_table import MappingScreen
from app.parsers.mapping import FieldMapping


class _FakeWindow:
    def __init__(self, result: tuple[str, ...] | None) -> None:
        self._result = result

    async def create_file_dialog(self, **kwargs: Any) -> tuple[str, ...] | None:
        return self._result


@pytest.fixture
def engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine: Engine) -> Session:
    return sessionmaker(bind=engine)()


def test_pick_file__returns_path_when_file_selected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    picked = tmp_path / "export.csv"
    monkeypatch.setattr(
        import_flow.app.native, "main_window", _FakeWindow((str(picked),))
    )

    result = asyncio.run(pick_file())

    assert result == picked


def test_pick_file__returns_none_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_flow.app.native, "main_window", _FakeWindow(None))

    result = asyncio.run(pick_file())

    assert result is None


def test_render_mapping__renders_mapping_screen_with_file_headers(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path)

    assert screen is not None
    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input, no button
    header_rows = middle_children[0].default_slot.children
    assert len(header_rows) == 3  # column header labels row + one row per CSV column


def test_render_mapping__shows_first_value_of_each_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path)

    assert screen is not None
    assert screen._row_for("Title").sample.text == "Some Paper"
    assert screen._row_for("DOI").sample.text == "10.1/xyz"


def test_render_mapping__notifies_and_returns_none_when_file_cannot_be_decoded(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(b"\x81")  # undefined in both utf-8-sig and cp1252
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path)  # must not raise

    assert screen is None


def test_render_mapping__returns_none_for_unknown_type(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    panes = shell()

    screen = render_mapping(panes.middle, "unknown", csv_path)

    assert screen is None


def test_import_csv__stores_records_and_returns_source_file_with_row_count(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\nOther Paper,10.1/abc\n")
    mapping = FieldMapping(targets={"Title": "title", "DOI": "doi"})

    source_file = import_csv(session, csv_path, mapping)
    session.commit()

    assert source_file.filename == "export.csv"
    assert source_file.format == "csv"
    assert source_file.row_count == 2
    assert isinstance(source_file.imported_at, datetime.datetime)


def test_import_csv__stores_skipped_rows_on_source_file(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n,\n")
    mapping = FieldMapping(targets={"Title": "title"})

    source_file = import_csv(session, csv_path, mapping)

    assert source_file.row_count == 1
    assert source_file.skipped_rows == [{"row_number": 3, "reason": "row is blank"}]


def test_import_file__dispatches_csv_to_import_csv(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    mapping = FieldMapping(targets={"Title": "title"})

    source_file = import_file(session, csv_path, "csv", mapping)

    assert source_file.format == "csv"
    assert source_file.row_count == 1


def test_import_file__unsupported_type_raises(session: Session, tmp_path: Path) -> None:
    xml_path = tmp_path / "export.xml"
    xml_path.write_text("<records/>\n")

    with pytest.raises(ValueError, match="unsupported file type"):
        import_file(session, xml_path, "endnote_xml", FieldMapping())


_RIS_TEXT = (
    "TY  - JOUR\nTI  - Some Paper\nAU  - Smith, J\nER  - \n\nTI  - Bad\nER  - \n"
)


def test_import_ris__stores_records_and_skipped_rows(
    session: Session, tmp_path: Path
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)
    mapping = FieldMapping(targets={"TI": "title"})

    source_file = import_ris(session, ris_path, mapping)
    session.commit()

    assert source_file.filename == "export.ris"
    assert source_file.format == "ris"
    assert source_file.row_count == 1
    assert source_file.skipped_rows == [
        {"row_number": 6, "reason": "record has no TY tag"}
    ]


def test_import_file__dispatches_ris_to_import_ris(
    session: Session, tmp_path: Path
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)

    source_file = import_file(session, ris_path, "ris", FieldMapping())

    assert source_file.format == "ris"


def test_render_mapping__ris_lists_distinct_tags_without_delimiter_input(
    tmp_path: Path,
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)
    panes = shell()

    screen = render_mapping(panes.middle, "ris", ris_path)

    assert screen is not None
    assert [row.header for row in screen.rows] == ["TI", "AU", "TY"]
    assert screen.list_delimiter_input is None
    assert screen.current_mapping().list_delimiter == "\n"


def test_render_mapping__ris_without_tags_notifies_and_returns_none(
    tmp_path: Path,
) -> None:
    ris_path = tmp_path / "empty.ris"
    ris_path.write_text("")
    panes = shell()

    assert render_mapping(panes.middle, "ris", ris_path) is None


def test_render_import_view__ris_type_renders_mapping_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)
    _pick(monkeypatch, ris_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)
    asyncio.run(view._select_file())

    view._set_type("ris")

    assert view.mapping_screen is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


_NBIB_TEXT = "PMID- 1\nTI  - Some Paper\nFAU - Smith, J\n\nTI  - Bad\n"


def test_import_nbib__stores_records_and_skipped_rows(
    session: Session, tmp_path: Path
) -> None:
    nbib_path = tmp_path / "export.nbib"
    nbib_path.write_text(_NBIB_TEXT)
    mapping = FieldMapping(targets={"TI": "title"})

    source_file = import_nbib(session, nbib_path, mapping)
    session.commit()

    assert source_file.filename == "export.nbib"
    assert source_file.format == "nbib"
    assert source_file.row_count == 1
    assert source_file.skipped_rows == [
        {"row_number": 5, "reason": "record has no PMID tag"}
    ]


def test_import_file__dispatches_nbib_to_import_nbib(
    session: Session, tmp_path: Path
) -> None:
    nbib_path = tmp_path / "export.nbib"
    nbib_path.write_text(_NBIB_TEXT)

    source_file = import_file(session, nbib_path, "nbib", FieldMapping())

    assert source_file.format == "nbib"


def test_render_mapping__nbib_lists_distinct_tags_without_delimiter_input(
    tmp_path: Path,
) -> None:
    nbib_path = tmp_path / "export.nbib"
    nbib_path.write_text(_NBIB_TEXT)
    panes = shell()

    screen = render_mapping(panes.middle, "nbib", nbib_path)

    assert screen is not None
    assert [row.header for row in screen.rows] == ["PMID", "TI", "FAU"]
    assert screen.list_delimiter_input is None
    assert screen.current_mapping().list_delimiter == "\n"


def test_render_mapping__nbib_without_tags_notifies_and_returns_none(
    tmp_path: Path,
) -> None:
    nbib_path = tmp_path / "empty.nbib"
    nbib_path.write_text("")
    panes = shell()

    assert render_mapping(panes.middle, "nbib", nbib_path) is None


def test_render_import_view__nbib_type_renders_mapping_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    nbib_path = tmp_path / "export.nbib"
    nbib_path.write_text(_NBIB_TEXT)
    _pick(monkeypatch, nbib_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)
    asyncio.run(view._select_file())

    view._set_type("nbib")

    assert view.mapping_screen is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


_BIBTEX_TEXT = (
    "@article{key1, title = {Some Paper}, author = {Smith, J}}\n"
    "@article{title = {No key}}\n"
)


def test_import_bibtex__stores_records_and_skipped_rows(
    session: Session, tmp_path: Path
) -> None:
    bibtex_path = tmp_path / "export.bib"
    bibtex_path.write_text(_BIBTEX_TEXT)
    mapping = FieldMapping(targets={"title": "title"})

    source_file = import_bibtex(session, bibtex_path, mapping)
    session.commit()

    assert source_file.filename == "export.bib"
    assert source_file.format == "bibtex"
    assert source_file.row_count == 1
    assert source_file.skipped_rows == [
        {"row_number": 2, "reason": "entry has no citation key"}
    ]


def test_import_file__dispatches_bibtex_to_import_bibtex(
    session: Session, tmp_path: Path
) -> None:
    bibtex_path = tmp_path / "export.bib"
    bibtex_path.write_text(_BIBTEX_TEXT)

    source_file = import_file(session, bibtex_path, "bibtex", FieldMapping())

    assert source_file.format == "bibtex"


def test_render_mapping__bibtex_lists_fields_with_delimiter_input(
    tmp_path: Path,
) -> None:
    bibtex_path = tmp_path / "export.bib"
    bibtex_path.write_text(_BIBTEX_TEXT)
    panes = shell()

    screen = render_mapping(panes.middle, "bibtex", bibtex_path)

    assert screen is not None
    assert [row.header for row in screen.rows] == ["title", "author", "@type", "@key"]
    assert screen.list_delimiter_input is not None
    assert screen.current_mapping().list_delimiter == ";"


def test_render_mapping__bibtex_without_entries_notifies_and_returns_none(
    tmp_path: Path,
) -> None:
    bibtex_path = tmp_path / "empty.bib"
    bibtex_path.write_text("")
    panes = shell()

    assert render_mapping(panes.middle, "bibtex", bibtex_path) is None


def test_render_import_view__bibtex_file_is_detected_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    bibtex_path = tmp_path / "export.bib"
    bibtex_path.write_text(_BIBTEX_TEXT)
    _pick(monkeypatch, bibtex_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    asyncio.run(view._select_file())

    assert view.file_type == "bibtex"
    assert view.mapping_screen is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


def _pick(monkeypatch: pytest.MonkeyPatch, path: Path | None) -> None:
    monkeypatch.setattr(
        import_flow.app.native,
        "main_window",
        _FakeWindow((str(path),) if path is not None else None),
    )


def test_render_import_view__initial_state_has_no_file_and_disabled_buttons() -> None:
    panes = shell()

    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    assert view.path is None
    assert view.file_type == "unknown"
    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False


def test_render_import_view__selecting_file_updates_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    txt_path = tmp_path / "export.txt"
    txt_path.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, txt_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    asyncio.run(view._select_file())

    assert view.path == txt_path
    # type is not detected, so no mapping renders yet
    assert view.mapping_screen is None
    outer_column = panes.middle.default_slot.children[0]
    file_row = outer_column.default_slot.children[0]
    assert file_row.default_slot.children[0].text == "export.txt"  # type: ignore[attr-defined]


def test_render_import_view__mapping_renders_inline_and_enables_import_without_confirm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    txt_path = tmp_path / "export.txt"
    txt_path.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, txt_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)
    asyncio.run(view._select_file())

    assert view.import_button is not None
    assert view.import_button.enabled is False  # type not detected
    assert view.mapping_screen is None

    view._set_type("csv")

    # mapping table rendered automatically, no "Check Mapping"/confirm click needed
    assert view.mapping_screen is not None
    assert view.import_button.enabled is True


def test_render_import_view__selecting_file_prefills_detected_type_and_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    txt_path = tmp_path / "pubmed.txt"
    txt_path.write_text("PMID- 1\nOWN - NLM\nTI  - A title\n")
    _pick(monkeypatch, txt_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    asyncio.run(view._select_file())

    assert view.file_type == "nbib"
    assert view.source == "pubmed"
    assert view.mapping_screen is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


def test_render_import_view__undetected_file_resets_type_and_source_to_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("just some notes\n")
    _pick(monkeypatch, txt_path)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)
    view._set_type("csv")
    view._set_source("pubmed")

    asyncio.run(view._select_file())

    assert view.file_type == "unknown"
    assert view.source == "unknown"
    assert view.import_button is not None
    assert view.import_button.enabled is False


def test_render_import_view__import_reads_live_mapping_edits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Scopus Author ID\nabc123\n")
    _pick(monkeypatch, csv_path)
    calls: list[tuple[Path, str, FieldMapping, str]] = []
    view = render_import_view(
        panes.middle, on_import=lambda p, t, m, s: calls.append((p, t, m, s))
    )
    asyncio.run(view._select_file())
    view._set_type("csv")
    assert view.mapping_screen is not None

    view.mapping_screen.set_target("Scopus Author ID", "authors")
    view._import()

    assert calls == [
        (
            csv_path,
            "csv",
            FieldMapping(targets={"Scopus Author ID": "authors"}),
            "unknown",
        )
    ]


def test_render_import_view__selecting_new_file_rerenders_mapping_from_new_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first_csv = tmp_path / "export.csv"
    first_csv.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, first_csv)
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)
    asyncio.run(view._select_file())
    view._set_type("csv")
    assert view.mapping_screen is not None
    assert [row.header for row in view.mapping_screen.rows] == ["Title"]

    other_csv = tmp_path / "other.csv"
    other_csv.write_text("DOI\n10.1/xyz\n")
    _pick(monkeypatch, other_csv)
    asyncio.run(view._select_file())

    assert view.mapping_screen is not None
    assert [row.header for row in view.mapping_screen.rows] == ["DOI"]
    assert view.import_button is not None
    assert view.import_button.enabled is True


def test_render_import_view__import_disabled_when_csv_file_cannot_be_decoded(
    tmp_path: Path,
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_bytes(b"\x81")  # undefined in both utf-8-sig and cp1252
    view = ImportView(middle=panes.middle, on_import=lambda p, t, m, s: None)
    view.path = csv_path

    view._set_type("csv")  # must not raise

    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False


_PUBMED_NBIB_TEXT = (
    "PMID- 1\nTI  - [Not Available].\nTT  - Original.\nPG  - 521-2\n"
    "TA  - Nature\nJT  - Nature reviews\n"
)


def test_render_mapping__pubmed_nbib_suggests_jt_not_ta(tmp_path: Path) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    panes = shell()

    screen = render_mapping(panes.middle, "nbib", nbib_path, "pubmed")

    assert screen is not None
    targets = screen.current_mapping().targets
    assert targets["JT"] == "journal"
    assert "TA" not in targets


def test_render_mapping__pubmed_csv_uses_comma_delimiter(tmp_path: Path) -> None:
    csv_path = tmp_path / "pubmed.csv"
    csv_path.write_text('PMID,Authors\n1,"Romano M, Novacek MJ."\n')
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path, "pubmed")

    assert screen is not None
    assert screen.current_mapping().list_delimiter == ","


def test_render_mapping__scopus_csv_leaves_ignored_columns_unmapped(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "scopus.csv"
    csv_path.write_text("Conference name,Conference date,EID\nC,D,2-s2.0-1\n")
    panes = shell()

    screen = render_mapping(panes.middle, "csv", csv_path, "scopus")

    assert screen is not None
    targets = screen.current_mapping().targets
    assert targets["Conference name"] == "conference_name"
    assert "Conference date" not in targets


def test_render_mapping__scopus_ris_uses_profile_aliases(tmp_path: Path) -> None:
    ris_path = tmp_path / "scopus.ris"
    ris_path.write_text("TY  - JOUR\nM3  - Article\nDB  - Scopus\nER  - \n")
    panes = shell()

    screen = render_mapping(panes.middle, "ris", ris_path, "scopus")

    assert screen is not None
    targets = screen.current_mapping().targets
    assert targets["M3"] == "publication_type"
    assert "TY" not in targets


def test_import_file__pubmed_applies_profile_and_stores_source(
    session: Session, tmp_path: Path
) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    mapping = FieldMapping(targets={"TI": "title", "PG": "pages"})

    source_file = import_file(session, nbib_path, "nbib", mapping, "pubmed")
    session.commit()

    assert source_file.source == "pubmed"
    record = session.query(Record).one()
    assert record.title == "Original."
    assert record.pages == "521-522"


def test_import_file__pubmed_ris_imports_generically_and_stores_source(
    session: Session, tmp_path: Path
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)

    source_file = import_file(session, ris_path, "ris", FieldMapping(), "pubmed")

    assert source_file.source == "pubmed"
    assert source_file.row_count == 1


def test_import_file__unknown_source_stores_no_source(
    session: Session, tmp_path: Path
) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    mapping = FieldMapping(targets={"PG": "pages"})

    source_file = import_file(session, nbib_path, "nbib", mapping, "unknown")
    session.commit()

    assert source_file.source is None
    assert session.query(Record).one().pages == "521-2"


def test_render_import_view__source_change_rerenders_mapping_and_is_passed_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    _pick(monkeypatch, nbib_path)
    calls: list[str] = []
    view = render_import_view(
        panes.middle, on_import=lambda p, t, m, s: calls.append(s)
    )
    asyncio.run(view._select_file())
    view._set_type("nbib")

    view._set_source("pubmed")

    assert view.mapping_screen is not None
    assert "TA" not in view.mapping_screen.current_mapping().targets
    view._import()
    assert calls == ["pubmed"]


def _result(screen: MappingScreen, header: str) -> str:
    text: str = screen._row_for(header).result.text
    return text


def test_render_mapping__result_applies_pubmed_nbib_profile(tmp_path: Path) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT + "IS  - 1234-5678 (Print)\n")
    panes = shell()

    screen = render_mapping(panes.middle, "nbib", nbib_path, "pubmed")

    assert screen is not None
    assert _result(screen, "PG") == "521-522"
    assert _result(screen, "TI") == "Original."
    assert _result(screen, "IS") == "1234-5678"


def test_render_mapping__result_without_source_skips_profile(tmp_path: Path) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    panes = shell()

    screen = render_mapping(panes.middle, "nbib", nbib_path)

    assert screen is not None
    assert _result(screen, "PG") == "521-2"


def test_render_mapping__nbib_result_combines_fau_auid_and_ad(tmp_path: Path) -> None:
    nbib_path = tmp_path / "authors.nbib"
    nbib_path.write_text(
        "PMID- 1\nFAU - Smith, John\nAUID- ORCID: 0000-0001-2345-6789\n"
        "AD  - University X\n"
    )
    panes = shell()

    screen = render_mapping(panes.middle, "nbib", nbib_path)

    assert screen is not None
    expected = "Smith, John (ORCID 0000-0001-2345-6789; University X)"
    assert [_result(screen, tag) for tag in ("FAU", "AUID", "AD")] == [expected] * 3


def test_render_import_view__unknown_type_shows_select_type_tooltip() -> None:
    panes = shell()

    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    assert view.import_button is not None
    tooltips = [
        t.text
        for t in panes.middle.descendants()
        if isinstance(t, Tooltip)
        and t.props["target"] == f"#{view.import_button.html_id}"
    ]
    assert tooltips == ["please select the type"]


_NO_PROFILE_NOTICE = (
    "No profile for this source/type combination — using the default parser."
)


def _visible_notices(middle: Any) -> list[str]:
    icons = [
        icon
        for icon in middle.descendants()
        if isinstance(icon, Icon) and "invisible" not in icon.classes
    ]
    return [
        tooltip.text
        for tooltip in middle.descendants()
        if isinstance(tooltip, Tooltip)
        and any(tooltip.props["target"] == f"#{icon.html_id}" for icon in icons)
    ]


def test_render_import_view__mismatched_source_and_type_shows_notice() -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    view._set_source("pubmed")
    view._set_type("ris")

    assert _visible_notices(panes.middle) == [_NO_PROFILE_NOTICE]


@pytest.mark.parametrize(
    ("source", "file_type"),
    [("pubmed", "nbib"), ("unknown", "ris"), ("pubmed", "unknown")],
)
def test_render_import_view__no_notice_unless_both_set_without_profile(
    source: str, file_type: str
) -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda p, t, m, s: None)

    view._set_source(source)
    view._set_type(file_type)

    assert _visible_notices(panes.middle) == []
