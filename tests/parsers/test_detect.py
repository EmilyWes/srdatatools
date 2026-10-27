from pathlib import Path

import pytest
from openpyxl import Workbook

from app.parsers import detect
from app.parsers.detect import detect_source, detect_type

_DATA_DIR = Path(__file__).parent.parent / "data" / "general"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _workbook(tmp_path: Path, name: str, rows: list[list[object]]) -> Path:
    workbook = Workbook()
    for row in rows:
        workbook.worksheets[0].append(row)
    path = tmp_path / name
    workbook.save(path)
    return path


def test_detect_type__ris_content() -> None:
    assert detect_type(_DATA_DIR / "scopus_style.ris") == "ris"


def test_detect_type__nbib_content() -> None:
    assert detect_type(_DATA_DIR / "pubmed_style.nbib") == "nbib"


def test_detect_type__cp1252_csv_content() -> None:
    assert detect_type(_DATA_DIR / "cp1252_encoded.csv") == "csv"


def test_detect_type__bibtex_content() -> None:
    assert detect_type(_DATA_DIR / "bibtex_style.bib") == "bibtex"


def test_detect_type__tab_delimited_content_is_tsv() -> None:
    assert detect_type(_DATA_DIR / "tab_delimited.tsv") == "tsv"


def test_detect_type__bibtex_after_free_text_header(tmp_path: Path) -> None:
    text = "Scopus\nEXPORT DATE: 22 October 2026\n\n@ARTICLE{key1,\n\ttitle = {T}\n}\n"
    path = _write(tmp_path, "export.txt", text)

    assert detect_type(path) == "bibtex"


def test_detect_type__only_comment_entries_is_not_bibtex(tmp_path: Path) -> None:
    path = _write(tmp_path, "notes.txt", "@comment{note}\n@string{a = {b}}\n")

    assert detect_type(path) is None


def test_detect_type__nbib_in_txt_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "pubmed.txt", "\nPMID- 1\nOWN - NLM\nTI  - Title\n")

    assert detect_type(path) == "nbib"


def test_detect_type__semicolon_csv_in_txt_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "export.txt", "Title;Year\nA study;2020\n")

    assert detect_type(path) == "csv"


def test_detect_type__tab_delimited_csv_extension_is_tsv(tmp_path: Path) -> None:
    path = _write(tmp_path, "export.csv", "Title\tYear\nA, B study\t2020\n")

    assert detect_type(path) == "tsv"


def test_detect_type__prose_with_commas_is_not_csv(tmp_path: Path) -> None:
    path = _write(tmp_path, "notes.txt", "First, some notes, here.\nThen more text.\n")

    assert detect_type(path) is None


def test_detect_type__header_without_data_row_is_not_csv(tmp_path: Path) -> None:
    path = _write(tmp_path, "headers.txt", "Title,Year,DOI\n")

    assert detect_type(path) is None


def test_detect_type__csv_with_long_first_row(tmp_path: Path) -> None:
    abstract = "word " * 1000
    path = _write(tmp_path, "export.txt", f'Title,Abstract\nA study,"{abstract}"\n')

    assert detect_type(path) == "csv"


def test_detect_type__content_beats_wrong_extension(tmp_path: Path) -> None:
    path = _write(tmp_path, "export.csv", "TY  - JOUR\nTI  - Title\nER  - \n")

    assert detect_type(path) == "ris"


def test_detect_type__ignores_content_after_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detect, "_DETECT_PREFIX_SIZE", 20)
    text = "free text header...\n@article{k, title = {T}}\n"
    path = _write(tmp_path, "export.txt", text)

    assert detect_type(path) is None


def test_detect_type__falls_back_to_extension_for_unrecognised_content(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "empty.RIS", "")

    assert detect_type(path) == "ris"


def test_detect_type__falls_back_to_bib_extension(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.bib", "")

    assert detect_type(path) == "bibtex"


def test_detect_type__falls_back_to_tsv_extension(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.tsv", "")

    assert detect_type(path) == "tsv"


def test_detect_type__xlsx_workbook_is_excel(tmp_path: Path) -> None:
    path = _workbook(tmp_path, "export.xlsx", [["Title", "DOI"], ["A", "10.1/a"]])

    assert detect_type(path) == "excel"


def test_detect_type__uppercase_xlsx_extension_is_excel(tmp_path: Path) -> None:
    path = _workbook(tmp_path, "EXPORT.XLSX", [["Title"], ["A"]])

    assert detect_type(path) == "excel"


def test_detect_type__falls_back_to_extension_for_undecodable_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.nbib"
    path.write_bytes(b"\x81\x8d\x8f\x90\x9d")

    assert detect_type(path) == "nbib"


def test_detect_type__unrecognised_content_and_extension_returns_none(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "notes.txt", "just some notes\n")

    assert detect_type(path) is None


def test_detect_source__pubmed_nbib() -> None:
    assert detect_source(_DATA_DIR / "pubmed_style.nbib", "nbib") == "pubmed"


def test_detect_source__pubmed_csv(tmp_path: Path) -> None:
    path = _write(tmp_path, "pubmed.csv", "PMID,Title,Citation,Journal/Book\n1,A,B,C\n")

    assert detect_source(path, "csv") == "pubmed"


def test_detect_source__scopus_csv(tmp_path: Path) -> None:
    path = _write(tmp_path, "scopus.csv", '"Authors","Title","EID"\n"A","T","E"\n')

    assert detect_source(path, "csv") == "scopus"


def test_detect_source__scopus_ris(tmp_path: Path) -> None:
    path = _write(tmp_path, "scopus.ris", "TY  - JOUR\nDB  - Scopus\nER  - \n")

    assert detect_source(path, "ris") == "scopus"


def test_detect_source__scopus_bibtex(tmp_path: Path) -> None:
    text = "Scopus\n\n@ARTICLE{k,\n\ttitle = {T},\n\tsource = {Scopus}\n}\n"
    path = _write(tmp_path, "scopus.bib", text)

    assert detect_source(path, "bibtex") == "scopus"


def test_detect_source__ignores_content_after_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detect, "_DETECT_PREFIX_SIZE", 22)
    text = "TY  - JOUR\nTI  - Title\nDB  - Scopus\nER  - \n"
    path = _write(tmp_path, "scopus.ris", text)

    assert detect_source(path, "ris") is None


def test_detect_source__no_matching_profile_returns_none() -> None:
    assert detect_source(_DATA_DIR / "scopus_style.ris", "ris") is None


def test_detect_source__tsv_has_no_profile(tmp_path: Path) -> None:
    path = _write(tmp_path, "scopus.tsv", "Authors\tTitle\tEID\nA\tT\tE\n")

    assert detect_source(path, "tsv") is None


def test_detect_source__excel_has_no_profile(tmp_path: Path) -> None:
    path = _workbook(tmp_path, "scopus.xlsx", [["Authors", "Title", "EID"]])

    assert detect_source(path, "excel") is None


def test_detect_source__undecodable_file_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "broken.nbib"
    path.write_bytes(b"\x81\x8d\x8f\x90\x9d")

    assert detect_source(path, "nbib") is None
