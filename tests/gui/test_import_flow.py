import asyncio
import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from nicegui.element import Element
from nicegui.elements.icon import Icon
from nicegui.elements.tooltip import Tooltip
from openpyxl import Workbook
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ActivityLog, Base, Record
from app.gui import import_flow
from app.gui.import_flow import (
    ImportView,
    common_detection,
    import_bibtex,
    import_csv,
    import_excel,
    import_file,
    import_nbib,
    import_ris,
    import_tsv,
    pick_files,
    read_summary,
    render_import_view,
    render_mapping,
)
from app.gui.layout import shell
from app.gui.mapping_table import MappingScreen
from app.parsers.common import FileSummary
from app.parsers.mapping import FieldMapping
from tests.gui.clicks import click_and_wait


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


def test_pick_files__returns_all_selected_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "export.csv"
    second = tmp_path / "other.csv"
    monkeypatch.setattr(
        import_flow.app.native,
        "main_window",
        _FakeWindow((str(first), str(second))),
    )

    result = asyncio.run(pick_files())

    assert result == [first, second]


def test_pick_files__returns_empty_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(import_flow.app.native, "main_window", _FakeWindow(None))

    result = asyncio.run(pick_files())

    assert result == []


def test_common_detection__agreeing_files_keep_values() -> None:
    detected = [("nbib", "pubmed"), ("nbib", "pubmed")]

    assert common_detection(detected) == ("nbib", "pubmed")


def test_common_detection__differing_values_become_unknown() -> None:
    assert common_detection([("nbib", "pubmed"), ("csv", "pubmed")]) == (
        "unknown",
        "pubmed",
    )
    assert common_detection([("csv", "pubmed"), ("csv", "unknown")]) == (
        "csv",
        "unknown",
    )


_EMPTY_SUMMARY = FileSummary({}, {}, 0)


def _summary(file_type: str, path: Path) -> FileSummary:
    summary = read_summary(file_type, path)
    assert summary is not None
    return summary


def _render_mapping(
    container: Element, file_type: str, path: Path, source: str = "unknown"
) -> MappingScreen | None:
    summary = read_summary(file_type, path)
    assert summary is not None
    return render_mapping(container, file_type, path.name, summary, source)


def test_render_mapping__renders_mapping_screen_with_file_headers(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")
    panes = shell()

    screen = _render_mapping(panes.middle, "csv", csv_path)

    assert screen is not None
    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 2  # header rows column + delimiter input, no button
    header_rows = middle_children[0].default_slot.children
    assert len(header_rows) == 3  # column header labels row + one row per CSV column


def test_render_mapping__shows_first_value_of_each_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n")
    panes = shell()

    screen = _render_mapping(panes.middle, "csv", csv_path)

    assert screen is not None
    assert screen._row_for("Title").sample.text == "Some Paper"
    assert screen._row_for("DOI").sample.text == "10.1/xyz"


def test_render_mapping__returns_none_for_unknown_type(tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    panes = shell()

    screen = render_mapping(
        panes.middle,
        "unknown",
        csv_path.name,
        FileSummary({"Title": "Some Paper"}, {}, 1),
    )

    assert screen is None


def test_import_csv__stores_records_and_returns_source_file_with_row_count(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\nOther Paper,10.1/abc\n")
    mapping = FieldMapping(targets={"Title": "title", "DOI": "doi"})

    source_file = import_csv(session, csv_path, mapping, _summary("csv", csv_path))
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

    source_file = import_csv(session, csv_path, mapping, _summary("csv", csv_path))

    assert source_file.row_count == 1
    assert source_file.skipped_rows == [{"row_number": 3, "reason": "row is blank"}]


def test_import_file__dispatches_csv_to_import_csv(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    mapping = FieldMapping(targets={"Title": "title"})

    source_file = import_file(
        session, csv_path, "csv", mapping, _summary("csv", csv_path)
    )

    assert source_file.format == "csv"
    assert source_file.row_count == 1


def test_import_tsv__stores_records_with_tsv_format(
    session: Session, tmp_path: Path
) -> None:
    tsv_path = tmp_path / "export.tsv"
    tsv_path.write_text("Title\tDOI\nA, B study\t10.1/xyz\nOther Paper\t10.1/abc\n")
    mapping = FieldMapping(targets={"Title": "title", "DOI": "doi"})

    source_file = import_tsv(session, tsv_path, mapping, _summary("tsv", tsv_path))
    session.commit()

    assert source_file.format == "tsv"
    assert source_file.row_count == 2
    assert source_file.skipped_rows == []


def test_import_file__dispatches_tsv_to_import_tsv(
    session: Session, tmp_path: Path
) -> None:
    tsv_path = tmp_path / "export.tsv"
    tsv_path.write_text("Title\nSome Paper\n")
    mapping = FieldMapping(targets={"Title": "title"})

    source_file = import_file(
        session, tsv_path, "tsv", mapping, _summary("tsv", tsv_path)
    )

    assert source_file.format == "tsv"
    assert source_file.row_count == 1


def test_import_file__writes_activity_log_row(session: Session, tmp_path: Path) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\n,\nOther Paper,10.1/abc\n")
    mapping = FieldMapping(targets={"Title": "title"})

    import_file(session, csv_path, "csv", mapping, _summary("csv", csv_path))
    session.commit()

    entry = session.query(ActivityLog).one()
    assert entry.message == "Imported from:\nexport.csv\nProcessed: 2\nSkipped: 1"


def test_import_file__saves_mapping_suggestion_and_summary(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title,DOI\nSome Paper,10.1/xyz\nOther Paper,\n")
    mapping = FieldMapping(targets={"Title": "title"}, list_delimiter="|")

    source_file = import_file(
        session, csv_path, "csv", mapping, _summary("csv", csv_path)
    )

    assert source_file.field_mapping == asdict(mapping)
    assert source_file.suggested_mapping["targets"] == {
        "Title": "title",
        "DOI": "doi",
    }
    assert source_file.file_summary == {
        "samples": {"Title": "Some Paper", "DOI": "10.1/xyz"},
        "filled": {"Title": 2, "DOI": 1},
        "total_rows": 2,
    }


def test_import_file__unsupported_type_raises(session: Session, tmp_path: Path) -> None:
    xml_path = tmp_path / "export.xml"
    xml_path.write_text("<records/>\n")

    with pytest.raises(ValueError, match="unsupported file type"):
        import_file(session, xml_path, "endnote_xml", FieldMapping(), _EMPTY_SUMMARY)


_RIS_TEXT = (
    "TY  - JOUR\nTI  - Some Paper\nAU  - Smith, J\nER  - \n\nTI  - Bad\nER  - \n"
)


def test_import_ris__stores_records_and_skipped_rows(
    session: Session, tmp_path: Path
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)
    mapping = FieldMapping(targets={"TI": "title"})

    source_file = import_ris(session, ris_path, mapping, _summary("ris", ris_path))
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

    source_file = import_file(
        session, ris_path, "ris", FieldMapping(), _summary("ris", ris_path)
    )

    assert source_file.format == "ris"


def test_import_file__saves_ris_suggestion_with_newline_delimiter(
    session: Session, tmp_path: Path
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)

    source_file = import_file(
        session, ris_path, "ris", FieldMapping(), _summary("ris", ris_path)
    )

    assert source_file.suggested_mapping["list_delimiter"] == "\n"
    assert set(source_file.file_summary["samples"]) == {"TI", "AU", "TY"}


def test_render_mapping__ris_lists_distinct_tags_without_delimiter_input(
    tmp_path: Path,
) -> None:
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)
    panes = shell()

    screen = _render_mapping(panes.middle, "ris", ris_path)

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

    assert _render_mapping(panes.middle, "ris", ris_path) is None


def test_render_import_view__ris_type_renders_mapping_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    ris_path = tmp_path / "export.ris"
    ris_path.write_text(_RIS_TEXT)
    _pick(monkeypatch, ris_path)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._select_files())

    asyncio.run(view._set_type("ris"))

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

    source_file = import_nbib(session, nbib_path, mapping, _summary("nbib", nbib_path))
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

    source_file = import_file(
        session, nbib_path, "nbib", FieldMapping(), _summary("nbib", nbib_path)
    )

    assert source_file.format == "nbib"


def test_render_mapping__nbib_lists_distinct_tags_without_delimiter_input(
    tmp_path: Path,
) -> None:
    nbib_path = tmp_path / "export.nbib"
    nbib_path.write_text(_NBIB_TEXT)
    panes = shell()

    screen = _render_mapping(panes.middle, "nbib", nbib_path)

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

    assert _render_mapping(panes.middle, "nbib", nbib_path) is None


def test_render_import_view__nbib_type_renders_mapping_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    nbib_path = tmp_path / "export.nbib"
    nbib_path.write_text(_NBIB_TEXT)
    _pick(monkeypatch, nbib_path)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._select_files())

    asyncio.run(view._set_type("nbib"))

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

    source_file = import_bibtex(
        session, bibtex_path, mapping, _summary("bibtex", bibtex_path)
    )
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

    source_file = import_file(
        session, bibtex_path, "bibtex", FieldMapping(), _summary("bibtex", bibtex_path)
    )

    assert source_file.format == "bibtex"


def test_render_mapping__bibtex_lists_fields_with_delimiter_input(
    tmp_path: Path,
) -> None:
    bibtex_path = tmp_path / "export.bib"
    bibtex_path.write_text(_BIBTEX_TEXT)
    panes = shell()

    screen = _render_mapping(panes.middle, "bibtex", bibtex_path)

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

    assert _render_mapping(panes.middle, "bibtex", bibtex_path) is None


def test_render_import_view__bibtex_file_is_detected_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    bibtex_path = tmp_path / "export.bib"
    bibtex_path.write_text(_BIBTEX_TEXT)
    _pick(monkeypatch, bibtex_path)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.file_type == "bibtex"
    assert view.mapping_screen is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


def test_render_mapping__tsv_lists_columns_with_delimiter_input(
    tmp_path: Path,
) -> None:
    tsv_path = tmp_path / "export.tsv"
    tsv_path.write_text("Title\tAuthors\nA, B study\tSmith, J; Doe, J\n")
    panes = shell()

    screen = _render_mapping(panes.middle, "tsv", tsv_path)

    assert screen is not None
    assert [row.header for row in screen.rows] == ["Title", "Authors"]
    assert screen.list_delimiter_input is not None


def test_render_import_view__tsv_file_is_detected_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    tsv_path = tmp_path / "export.tsv"
    tsv_path.write_text("Title\tYear\nSome Paper\t2020\n")
    _pick(monkeypatch, tsv_path)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.file_type == "tsv"
    assert view.mapping_screen is not None
    assert view.import_button is not None
    assert view.import_button.enabled is True


def _pick(monkeypatch: pytest.MonkeyPatch, *paths: Path) -> None:
    monkeypatch.setattr(
        import_flow.app.native,
        "main_window",
        _FakeWindow(tuple(str(path) for path in paths) or None),
    )


def test_render_import_view__initial_state_has_no_file_and_disabled_buttons() -> None:
    panes = shell()

    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    assert view.paths == []
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
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.paths == [txt_path]
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
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._select_files())

    assert view.import_button is not None
    assert view.import_button.enabled is False  # type not detected
    assert view.mapping_screen is None

    asyncio.run(view._set_type("csv"))

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
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

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
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._set_type("csv"))
    view._set_source("pubmed")

    asyncio.run(view._select_files())

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
    calls: list[tuple[list[tuple[Path, FileSummary]], str, FieldMapping, str]] = []
    view = render_import_view(
        panes.middle,
        on_import=lambda f, t, m, s, sh: calls.append((f, t, m, s)),
    )
    asyncio.run(view._select_files())
    asyncio.run(view._set_type("csv"))
    assert view.mapping_screen is not None

    view.mapping_screen.set_target("Scopus Author ID", "authors")
    view._import()

    assert calls == [
        (
            [
                (
                    csv_path,
                    FileSummary(
                        {"Scopus Author ID": "abc123"}, {"Scopus Author ID": 1}, 1
                    ),
                )
            ],
            "csv",
            FieldMapping(targets={"Scopus Author ID": "authors"}),
            "unknown",
        )
    ]


def test_render_import_view__import_button_awaits_async_on_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nA title\n")
    _pick(monkeypatch, csv_path)
    calls: list[Path] = []

    async def on_import(
        files: list[tuple[Path, FileSummary]],
        file_type: str,
        mapping: FieldMapping,
        source: str,
        sheet: str | None,
    ) -> None:
        calls.extend(path for path, _ in files)

    view = render_import_view(panes.middle, on_import=on_import)
    asyncio.run(view._select_files())
    assert view.import_button is not None

    click_and_wait(view.import_button, monkeypatch)

    assert calls == [csv_path]


def test_render_import_view__selecting_new_file_rerenders_mapping_from_new_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first_csv = tmp_path / "export.csv"
    first_csv.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, first_csv)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._select_files())
    asyncio.run(view._set_type("csv"))
    assert view.mapping_screen is not None
    assert [row.header for row in view.mapping_screen.rows] == ["Title"]

    other_csv = tmp_path / "other.csv"
    other_csv.write_text("DOI\n10.1/xyz\n")
    _pick(monkeypatch, other_csv)
    asyncio.run(view._select_files())

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
    view = ImportView(middle=panes.middle, on_import=lambda f, t, m, s, sh: None)
    view.paths = [csv_path]

    asyncio.run(view._set_type("csv"))  # must not raise

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

    screen = _render_mapping(panes.middle, "nbib", nbib_path, "pubmed")

    assert screen is not None
    targets = screen.current_mapping().targets
    assert targets["JT"] == "journal"
    assert "TA" not in targets


def test_render_mapping__pubmed_csv_uses_comma_delimiter(tmp_path: Path) -> None:
    csv_path = tmp_path / "pubmed.csv"
    csv_path.write_text('PMID,Authors\n1,"Romano M, Novacek MJ."\n')
    panes = shell()

    screen = _render_mapping(panes.middle, "csv", csv_path, "pubmed")

    assert screen is not None
    assert screen.current_mapping().list_delimiter == ","


def test_render_mapping__scopus_csv_leaves_ignored_columns_unmapped(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "scopus.csv"
    csv_path.write_text("Conference name,Conference date,EID\nC,D,2-s2.0-1\n")
    panes = shell()

    screen = _render_mapping(panes.middle, "csv", csv_path, "scopus")

    assert screen is not None
    targets = screen.current_mapping().targets
    assert targets["Conference name"] == "conference_name"
    assert "Conference date" not in targets


def test_render_mapping__scopus_ris_uses_profile_aliases(tmp_path: Path) -> None:
    ris_path = tmp_path / "scopus.ris"
    ris_path.write_text("TY  - JOUR\nM3  - Article\nDB  - Scopus\nER  - \n")
    panes = shell()

    screen = _render_mapping(panes.middle, "ris", ris_path, "scopus")

    assert screen is not None
    targets = screen.current_mapping().targets
    assert targets["M3"] == "publication_type"
    assert "TY" not in targets


def test_import_file__pubmed_applies_profile_and_stores_source(
    session: Session, tmp_path: Path
) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    mapping = FieldMapping(targets={"TI": "title", "TT": "title", "PG": "pages"})

    source_file = import_file(
        session, nbib_path, "nbib", mapping, _summary("nbib", nbib_path), "pubmed"
    )
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

    source_file = import_file(
        session, ris_path, "ris", FieldMapping(), _summary("ris", ris_path), "pubmed"
    )

    assert source_file.source == "pubmed"
    assert source_file.row_count == 1


def test_import_file__unknown_source_stores_no_source(
    session: Session, tmp_path: Path
) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    mapping = FieldMapping(targets={"PG": "pages"})

    source_file = import_file(
        session, nbib_path, "nbib", mapping, _summary("nbib", nbib_path), "unknown"
    )
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
        panes.middle, on_import=lambda f, t, m, s, sh: calls.append(s)
    )
    asyncio.run(view._select_files())
    asyncio.run(view._set_type("nbib"))

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

    screen = _render_mapping(panes.middle, "nbib", nbib_path, "pubmed")

    assert screen is not None
    assert _result(screen, "PG") == "521-522"
    assert _result(screen, "TI") == "Original."
    assert _result(screen, "IS") == "1234-5678"


def test_render_mapping__result_without_source_skips_profile(tmp_path: Path) -> None:
    nbib_path = tmp_path / "pubmed.nbib"
    nbib_path.write_text(_PUBMED_NBIB_TEXT)
    panes = shell()

    screen = _render_mapping(panes.middle, "nbib", nbib_path)

    assert screen is not None
    assert _result(screen, "PG") == "521-2"


def test_render_mapping__nbib_result_combines_fau_auid_and_ad(tmp_path: Path) -> None:
    nbib_path = tmp_path / "authors.nbib"
    nbib_path.write_text(
        "PMID- 1\nFAU - Smith, John\nAUID- ORCID: 0000-0001-2345-6789\n"
        "AD  - University X\n"
    )
    panes = shell()

    screen = _render_mapping(panes.middle, "nbib", nbib_path)

    assert screen is not None
    expected = "Smith, John (ORCID 0000-0001-2345-6789; University X)"
    assert [_result(screen, tag) for tag in ("FAU", "AUID", "AD")] == [expected] * 3


def test_render_import_view__unknown_type_shows_select_type_tooltip() -> None:
    panes = shell()

    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

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
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    view._set_source("pubmed")
    asyncio.run(view._set_type("ris"))

    assert _visible_notices(panes.middle) == [_NO_PROFILE_NOTICE]


@pytest.mark.parametrize(
    ("source", "file_type"),
    [("pubmed", "nbib"), ("unknown", "ris"), ("pubmed", "unknown")],
)
def test_render_import_view__no_notice_unless_both_set_without_profile(
    source: str, file_type: str
) -> None:
    panes = shell()
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    view._set_source(source)
    asyncio.run(view._set_type(file_type))

    assert _visible_notices(panes.middle) == []


_DETECTED_PUBMED_TEXT = "PMID- 1\nOWN - NLM\nTI  - A title\n"


def _file_row_children(middle: Element) -> list[Element]:
    outer_column = middle.default_slot.children[0]
    return list(outer_column.default_slot.children[0].default_slot.children)


def _tooltips_for(middle: Element, element: Element) -> list[str]:
    return [
        tooltip.text
        for tooltip in middle.descendants()
        if isinstance(tooltip, Tooltip)
        and tooltip.props.get("target") == f"#{element.html_id}"
    ]


def _warning_icons(middle: Element) -> list[Icon]:
    return [child for child in _file_row_children(middle) if isinstance(child, Icon)]


def test_render_import_view__multiple_files_shows_count_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = tmp_path / "export.ris"
    second = tmp_path / "other.ris"
    first.write_text(_RIS_TEXT)
    second.write_text(_RIS_TEXT)
    _pick(monkeypatch, first, second)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    label = _file_row_children(panes.middle)[0]
    assert label.text == "2 files selected"  # type: ignore[attr-defined]
    assert _tooltips_for(panes.middle, label) == ["export.ris, other.ris"]


def test_render_import_view__matching_files_no_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = tmp_path / "first.nbib"
    second = tmp_path / "second.nbib"
    first.write_text(_DETECTED_PUBMED_TEXT)
    second.write_text(_DETECTED_PUBMED_TEXT)
    _pick(monkeypatch, first, second)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert (view.file_type, view.source) == ("nbib", "pubmed")
    assert _warning_icons(panes.middle) == []


def test_render_import_view__mixed_sources_warns_and_prefills_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    nbib_path = tmp_path / "pubmed.nbib"
    ris_path = tmp_path / "export.ris"
    nbib_path.write_text(_DETECTED_PUBMED_TEXT)
    ris_path.write_text(_RIS_TEXT)
    _pick(monkeypatch, nbib_path, ris_path)
    notifications: list[str] = []
    monkeypatch.setattr(
        import_flow.ui,
        "notify",
        lambda message, type: notifications.append(type),
    )
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert (view.file_type, view.source) == ("unknown", "unknown")
    assert view.import_button is not None
    assert view.import_button.enabled is False
    assert notifications == ["warning"]
    [icon] = _warning_icons(panes.middle)
    [tooltip] = _tooltips_for(panes.middle, icon)
    assert "pubmed.nbib: NBIB, PubMed" in tooltip
    assert "export.ris: RIS, Unknown" in tooltip


def test_render_import_view__multiple_files_maps_merged_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("Title,Year\nA title,2020\n")
    second.write_text("Title,DOI\nB title,10.1/xyz\n")
    _pick(monkeypatch, first, second)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.mapping_screen is not None
    assert {row.header for row in view.mapping_screen.rows} == {"Title", "Year", "DOI"}
    assert view.mapping_screen._row_for("DOI").sample.text == "10.1/xyz"


def test_render_import_view__multiple_files_passes_each_own_summary_to_on_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("Title,Year\nA title,2020\n")
    second.write_text("Title,DOI\nB title,10.1/xyz\n")
    _pick(monkeypatch, first, second)
    calls: list[list[tuple[Path, FileSummary]]] = []
    view = render_import_view(
        panes.middle, on_import=lambda f, t, m, s, sh: calls.append(f)
    )
    asyncio.run(view._select_files())

    view._import()

    assert calls == [
        [
            (first, _summary("csv", first)),
            (second, _summary("csv", second)),
        ]
    ]


def _workbook(
    tmp_path: Path, sheets: dict[str, list[list[object]]], name: str = "export.xlsx"
) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    for sheet, rows in sheets.items():
        worksheet = workbook.create_sheet(sheet)
        for row in rows:
            worksheet.append(row)
    path = tmp_path / name
    workbook.save(path)
    return path


_TWO_SHEETS: dict[str, list[list[object]]] = {
    "Records": [["Title", "DOI"], ["First", "10.1/a"]],
    "Other": [["Name"], ["Second"], ["Third"]],
}


def test_import_excel__stores_records_with_excel_format_and_sheet(
    session: Session, tmp_path: Path
) -> None:
    path = _workbook(tmp_path, _TWO_SHEETS)
    mapping = FieldMapping(targets={"Name": "title"})
    summary = read_summary("excel", path, "Other")
    assert summary is not None

    source_file = import_excel(session, path, mapping, summary, sheet="Other")
    session.commit()

    assert source_file.format == "excel"
    assert source_file.sheet == "Other"
    assert source_file.row_count == 2
    assert [record.title for record in session.query(Record)] == ["Second", "Third"]


def test_import_file__dispatches_excel_to_import_excel(
    session: Session, tmp_path: Path
) -> None:
    path = _workbook(tmp_path, _TWO_SHEETS)
    mapping = FieldMapping(targets={"Name": "title"})

    source_file = import_file(
        session, path, "excel", mapping, _summary("excel", path), sheet="Other"
    )

    assert source_file.format == "excel"
    assert source_file.sheet == "Other"
    assert source_file.row_count == 2


def test_import_file__non_excel_type_stores_no_sheet(
    session: Session, tmp_path: Path
) -> None:
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")

    source_file = import_file(
        session, csv_path, "csv", FieldMapping(), _summary("csv", csv_path)
    )

    assert source_file.sheet is None


def test_read_summary__excel_reads_first_sheet_by_default(tmp_path: Path) -> None:
    path = _workbook(tmp_path, _TWO_SHEETS)

    summary = read_summary("excel", path)

    assert summary is not None
    assert list(summary.samples) == ["Title", "DOI"]


def test_render_mapping__excel_lists_columns_with_delimiter_input(
    tmp_path: Path,
) -> None:
    path = _workbook(tmp_path, {"Sheet1": [["Title", "Authors"], ["A", "B; C"]]})
    panes = shell()

    screen = _render_mapping(panes.middle, "excel", path)

    assert screen is not None
    assert [row.header for row in screen.rows] == ["Title", "Authors"]
    assert screen.list_delimiter_input is not None


def _sheet_select(middle: Element) -> Any:
    outer_column = middle.default_slot.children[0]
    return outer_column.default_slot.children[1]


def test_render_import_view__xlsx_file_lists_sheets_and_enables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    path = _workbook(tmp_path, _TWO_SHEETS)
    _pick(monkeypatch, path)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.file_type == "excel"
    assert view.sheets == ["Records", "Other"]
    assert view.sheet == "Records"
    select = _sheet_select(panes.middle)
    assert select.props["label"] == "Sheet"
    assert select.value == "Records"
    assert view.mapping_screen is not None
    assert {row.header for row in view.mapping_screen.rows} == {"Title", "DOI"}
    assert view.import_button is not None
    assert view.import_button.enabled is True


def test_render_import_view__non_excel_file_has_no_sheet_dropdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    csv_path = tmp_path / "export.csv"
    csv_path.write_text("Title\nSome Paper\n")
    _pick(monkeypatch, csv_path)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.sheets == []
    assert view.sheet is None
    assert not any(
        getattr(element, "props", {}).get("label") == "Sheet"
        for element in panes.middle.descendants()
    )


def test_render_import_view__changing_sheet_rerenders_mapping_and_is_passed_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    path = _workbook(tmp_path, _TWO_SHEETS)
    _pick(monkeypatch, path)
    calls: list[tuple[FileSummary, str | None]] = []
    view = render_import_view(
        panes.middle,
        on_import=lambda f, t, m, s, sh: calls.append((f[0][1], sh)),
    )
    asyncio.run(view._select_files())

    asyncio.run(view._set_sheet("Other"))

    assert view.sheet == "Other"
    assert _sheet_select(panes.middle).value == "Other"
    assert view.mapping_screen is not None
    assert [row.header for row in view.mapping_screen.rows] == ["Name"]
    view._import()
    assert calls == [(FileSummary({"Name": "Second"}, {"Name": 2}, 2), "Other")]


def test_render_import_view__new_file_resets_sheet_to_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = _workbook(tmp_path, _TWO_SHEETS, name="first.xlsx")
    second = _workbook(
        tmp_path, {"Main": [["Title"], ["A"]], "Other": [["DOI"], ["10.1/x"]]}
    )
    _pick(monkeypatch, first)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._select_files())
    asyncio.run(view._set_sheet("Other"))

    _pick(monkeypatch, second)
    asyncio.run(view._select_files())

    assert view.sheets == ["Main", "Other"]
    assert view.sheet == "Main"


def test_render_import_view__multiple_files_with_excel_type_disables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = _workbook(tmp_path, _TWO_SHEETS, name="first.xlsx")
    second = _workbook(tmp_path, _TWO_SHEETS, name="second.xlsx")
    _pick(monkeypatch, first, second)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)

    asyncio.run(view._select_files())

    assert view.file_type == "excel"
    assert view.sheets == []
    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False
    assert _tooltips_for(panes.middle, view.import_button) == [
        "Excel import takes one file at a time"
    ]


def test_render_import_view__multiple_files_switched_to_excel_disables_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    panes = shell()
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("Title\nA\n")
    second.write_text("Title\nB\n")
    _pick(monkeypatch, first, second)
    view = render_import_view(panes.middle, on_import=lambda f, t, m, s, sh: None)
    asyncio.run(view._select_files())

    asyncio.run(view._set_type("excel"))

    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False


def test_render_import_view__import_disabled_when_file_is_not_a_workbook(
    tmp_path: Path,
) -> None:
    panes = shell()
    path = tmp_path / "export.csv"
    path.write_text("Title\nSome Paper\n")
    view = ImportView(middle=panes.middle, on_import=lambda f, t, m, s, sh: None)
    view.paths = [path]

    asyncio.run(view._set_type("excel"))  # must not raise

    assert view.sheets == []
    assert view.mapping_screen is None
    assert view.import_button is not None
    assert view.import_button.enabled is False
