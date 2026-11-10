from pathlib import Path

from app.export.columns import ExportColumn, ExportRecord, export_columns
from app.export.csv_ import write_csv
from app.export.options import ExportOptions
from app.models.record import Author, PartialDate, Record
from app.parsers.csv_ import parse_csv_text, suggest_mapping

_RECORDS = [
    ExportRecord(
        id=1,
        record=Record(
            title="Deep learning, a review",
            authors=[
                Author(family_name="LeCun", given_name="Yann"),
                Author(family_name="Bengio", given_name="Yoshua"),
            ],
            abstract="First line.\nSecond line.",
            publication_date=PartialDate(year=2015, month=5),
            doi="10.1038/nature14539",
            keywords=["deep learning", "[MeSH] Humans"],
        ),
    ),
    ExportRecord(
        id=2,
        record=Record(
            title="Gradient-based learning applied to document recognition",
            authors=[Author(family_name="LeCun", given_name="Yann")],
            publication_date=PartialDate(year=1998),
            doi="10.1109/5.726791",
        ),
    ),
]


def _columns(names: dict[str, str], options: ExportOptions) -> list[ExportColumn]:
    columns = export_columns(_RECORDS, options)
    for column in columns:
        column.name = names.get(column.key, "")
    return columns


def _write(tmp_path: Path, names: dict[str, str], options: ExportOptions) -> bytes:
    path = tmp_path / "library.csv"
    write_csv(path, _columns(names, options), _RECORDS, options)
    return path.read_bytes()


def test_write_csv__only_named_columns_in_order_with_quoting(tmp_path: Path) -> None:
    options = ExportOptions(encoding="utf-8")

    content = _write(tmp_path, {"title": "Title", "doi": "DOI"}, options)

    assert content.decode() == (
        'Title,DOI\r\n"Deep learning, a review",10.1038/nature14539\r\n'
        "Gradient-based learning applied to document recognition,10.1109/5.726791\r\n"
    )


def test_write_csv__bom_by_default(tmp_path: Path) -> None:
    content = _write(tmp_path, {"doi": "DOI"}, ExportOptions())

    assert content.startswith(b"\xef\xbb\xbfDOI")


def test_write_csv__delimiter_option(tmp_path: Path) -> None:
    options = ExportOptions(encoding="utf-8", delimiter="\t")

    content = _write(tmp_path, {"title": "Title", "doi": "DOI"}, options)

    assert content.decode().splitlines()[1] == (
        "Deep learning, a review\t10.1038/nature14539"
    )


def test_write_csv__line_breaks_kept_inside_quotes_by_default(tmp_path: Path) -> None:
    content = _write(
        tmp_path, {"abstract": "Abstract"}, ExportOptions(encoding="utf-8")
    )

    assert '"First line.\nSecond line."' in content.decode()


def test_write_csv__line_breaks_replaced_with_space(tmp_path: Path) -> None:
    options = ExportOptions(encoding="utf-8", line_breaks="space")

    content = _write(tmp_path, {"abstract": "Abstract"}, options)

    assert content.decode().splitlines()[1] == "First line. Second line."


def test_write_csv__round_trips_through_the_csv_importer(tmp_path: Path) -> None:
    options = ExportOptions()
    columns = export_columns(_RECORDS, options)
    path = tmp_path / "library.csv"

    write_csv(path, columns, _RECORDS, options)

    text = path.read_text(encoding="utf-8-sig")
    headers = text.splitlines()[0].split(",")
    result = parse_csv_text(text, suggest_mapping(headers))
    assert not result.skipped
    first = result.rows[0].record
    assert first.title == "Deep learning, a review"
    assert [(a.family_name, a.given_name) for a in first.authors] == [
        ("LeCun", "Yann"),
        ("Bengio", "Yoshua"),
    ]
    assert first.doi == "10.1038/nature14539"
    assert first.publication_date == PartialDate(year=2015, month=5)
    assert "deep learning" in first.keywords
    assert result.rows[1].record.publication_date == PartialDate(year=1998)
