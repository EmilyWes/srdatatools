from pathlib import Path

import pytest

from app.gui.export.mapping import ExportRecord, export_fields
from app.gui.export.options import ExportOptions
from app.gui.export.ris import write_ris
from app.gui.export.ris_tags import (
    CURATED_TAGS,
    RIS_TAG_TO_NAME,
    TAG_PATTERN,
    TYPE_CODES,
    ris_type,
)
from app.helpers.format import PUBLICATION_TYPES
from app.models.record import Record
from app.parsers.ris import parse_ris_file, read_ris_tags, suggest_ris_mapping

_DATA = Path(__file__).parents[2] / "data"


def test_ris_tags__curated_tags_come_first() -> None:
    assert list(RIS_TAG_TO_NAME)[: len(CURATED_TAGS)] == list(CURATED_TAGS)


def test_ris_tags__all_are_valid_tags() -> None:
    assert all(TAG_PATTERN.fullmatch(tag) for tag in RIS_TAG_TO_NAME)


def test_ris_tags__end_tag_not_offered() -> None:
    assert "ER" not in RIS_TAG_TO_NAME


def test_type_codes__cover_every_standard_type() -> None:
    assert set(TYPE_CODES) == set(PUBLICATION_TYPES)


@pytest.mark.parametrize(
    ("stored", "code"),
    [
        ("Journal article", "JOUR"),
        ("Review", "JOUR"),
        ("Book chapter", "CHAP"),
        ("Conference paper", "CONF"),
        ("Conference abstract", "ABST"),
        ("Preprint", "UNPB"),
        ("Erratum", "JOUR"),
    ],
)
def test_ris_type__standard_type(stored: str, code: str) -> None:
    assert ris_type(stored) == code


@pytest.mark.parametrize("stored", ["CPAPER", "EDBOOK", "JOUR"])
def test_ris_type__ris_code_passes_through(stored: str) -> None:
    assert ris_type(stored) == stored


@pytest.mark.parametrize(
    ("stored", "code"),
    [("Article", "JOUR"), ("inproceedings", "CONF"), ("phdthesis", "THES")],
)
def test_ris_type__uncleaned_value_via_cleaning_aliases(stored: str, code: str) -> None:
    assert ris_type(stored) == code


def test_ris_type__first_line_of_several() -> None:
    assert ris_type("Article\nReview") == "JOUR"


@pytest.mark.parametrize("stored", [None, "", "Something else"])
def test_ris_type__unknown_or_empty_is_generic(stored: str | None) -> None:
    assert ris_type(stored) == "GEN"


_RECORDS = [
    ExportRecord(
        id=1,
        record=Record(
            title="Deep learning, a review",
            author_names=["LeCun, Yann", "Bengio, Yoshua"],
            abstract="First line.\nSecond line.",
            publication_date="2015/05/",
            publication_type="Journal article",
            pages="436-444",
            keywords={"": ["deep learning"], "MeSH": ["Humans"]},
            other_ids={"eid": "2-s2.0-1"},
        ),
    ),
    ExportRecord(
        id=2,
        record=Record(title="Gradient-based learning", publication_date="1998"),
    ),
]
_RIS = ExportOptions(file_type="ris")


def _write(
    tmp_path: Path, options: ExportOptions = _RIS, keys: set[str] | None = None
) -> str:
    columns = [
        column
        for column in export_fields(_RECORDS, options)
        if keys is None or column.key in keys
    ]
    path = tmp_path / "library.ris"
    write_ris(path, columns, _RECORDS, options)
    return path.read_bytes().decode("utf-8")


def test_write_ris__records_start_with_ty_and_end_with_er(tmp_path: Path) -> None:
    text = _write(tmp_path, keys={"publication_type", "title"})

    assert text == (
        "TY  - JOUR\r\nTI  - Deep learning, a review\r\nER  - \r\n\r\n"
        "TY  - GEN\r\nTI  - Gradient-based learning\r\nER  - \r\n\r\n"
    )


def test_write_ris__no_bom_by_default(tmp_path: Path) -> None:
    assert _write(tmp_path).startswith("TY")


def test_write_ris__bom_encoding_option(tmp_path: Path) -> None:
    options = _RIS.model_copy(update={"ris_encoding": "utf-8-sig"})

    assert _write(tmp_path, options).startswith("\ufeffTY")


def test_write_ris__one_line_per_value(tmp_path: Path) -> None:
    lines = _write(tmp_path).splitlines()

    assert "AU  - LeCun, Yann" in lines
    assert "AU  - Bengio, Yoshua" in lines
    assert "KW  - deep learning" in lines
    assert "KW  - Humans" in lines


def test_write_ris__values_joined_on_one_line(tmp_path: Path) -> None:
    options = _RIS.model_copy(update={"one_line_per_value": False})

    assert "AU  - LeCun, Yann; Bengio, Yoshua" in _write(tmp_path, options)


def test_write_ris__pages_split_or_full(tmp_path: Path) -> None:
    lines = _write(tmp_path).splitlines()
    unsplit = _RIS.model_copy(update={"split_pages": False})

    assert ["SP  - 436", "EP  - 444"] == [
        line for line in lines if line[:2] in ("SP", "EP")
    ]
    assert "SP  - 436-444" in _write(tmp_path, unsplit).splitlines()


def test_write_ris__year_and_date(tmp_path: Path) -> None:
    lines = _write(tmp_path).splitlines()

    assert "PY  - 2015" in lines
    assert "DA  - 2015/05//" in lines
    assert "PY  - 1998" in lines
    assert "DA  - 1998" in lines


def test_write_ris__note_name_prefixes_n1_lines(tmp_path: Path) -> None:
    columns = export_fields(_RECORDS, _RIS)
    eid = next(c for c in columns if c.key == "other_id:eid")
    path = tmp_path / "library.ris"

    write_ris(path, [eid], _RECORDS[:1], _RIS)
    named = path.read_text(encoding="utf-8")
    eid.note_name = ""
    write_ris(path, [eid], _RECORDS[:1], _RIS)

    assert "N1  - eid: 2-s2.0-1" in named
    assert "N1  - 2-s2.0-1" in path.read_text(encoding="utf-8")


def test_write_ris__one_n1_line_per_notes_line(tmp_path: Path) -> None:
    record = ExportRecord(id=1, record=Record(notes="Export Date: 1\nCited By: 4"))
    columns = [c for c in export_fields([record], _RIS) if c.key == "notes"]
    path = tmp_path / "library.ris"

    write_ris(path, columns, [record], _RIS)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["N1  - Export Date: 1", "N1  - Cited By: 4"]


def test_write_ris__line_breaks_replaced_with_space(tmp_path: Path) -> None:
    assert "AB  - First line. Second line." in _write(tmp_path).splitlines()


def test_write_ris__round_trips_through_the_ris_importer(tmp_path: Path) -> None:
    source = _DATA / "general" / "scopus_style.ris"
    mapping = suggest_ris_mapping(list(read_ris_tags(source).filled))
    imported = [row.record for row in parse_ris_file(source, mapping).rows]
    records = [ExportRecord(id=i, record=r) for i, r in enumerate(imported, 1)]
    path = tmp_path / "library.ris"

    write_ris(path, export_fields(records, _RIS), records, _RIS)
    mapping = suggest_ris_mapping(list(read_ris_tags(path).filled))
    result = parse_ris_file(path, mapping)

    assert not result.skipped
    fields = (
        "title",
        "author_names",
        "author_affiliations",
        "journal",
        "volume",
        "issue",
        "pages",
        "doi",
        "issn",
        "keywords",
        "url",
        "notes",
    )
    for before, row in zip(imported, result.rows, strict=True):
        after = row.record
        assert {f: getattr(after, f) for f in fields} == {
            f: getattr(before, f) for f in fields
        }
        assert after.publication_type == ris_type(before.publication_type)
        assert after.abstract == (
            " ".join(before.abstract.splitlines()) if before.abstract else None
        )
