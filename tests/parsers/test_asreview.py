from collections import Counter
from pathlib import Path

import pytest

from app.parsers.common import FileType, ParseResult
from app.parsers.csv_ import (
    parse_csv_file,
    parse_csv_text,
    read_csv_headers,
    suggest_mapping,
)
from app.parsers.detect import detect_source, detect_type
from app.parsers.excel import parse_excel_file, read_excel_headers
from app.parsers.mapping import FieldMapping
from app.parsers.profiles import apply_profile
from app.parsers.profiles.asreview import ASREVIEW
from app.parsers.ris import parse_ris_file, parse_ris_text, suggest_ris_mapping

_DATA_DIR = Path(__file__).parent.parent / "data" / "asreview"
_TSV_DELIMITER = "\t"

_RIS = """1.
TY  - JOUR
N1  - ASReview_relevant
N1  - EID: 2-s2.0-1
TI  - A
ER  -

2.
TY  - JOUR
N1  - asreview_group_id: 1
N1  - ASReview_irrelevant
TI  - B
ER  -

3.
TY  - JOUR
N1  - ASReview_not_seen
TI  - C
ER  -
"""


def _csv_mapping(headers: list[str], file_type: FileType = "csv") -> FieldMapping:
    profile = ASREVIEW.formats[file_type]
    return suggest_mapping(
        headers, profile.suggestions, profile.row_defaults, profile.ignored_keys
    )


def test_asreview_csv__suggests_label_and_rispy_columns() -> None:
    headers = [
        "",
        "title",
        "secondary_title",
        "author_address",
        "start_page",
        "end_page",
        "number",
        "type_of_reference",
        "asreview_group_id",
        "asreview_label",
        "asreview_time",
        "asreview_note",
    ]

    targets = {key: row.target for key, row in _csv_mapping(headers).rows.items()}

    assert targets == {
        "title": "title",
        "start_page": "pages",
        "end_page": "pages",
        "number": "issue",
        "type_of_reference": "publication_type",
        "asreview_label": "label",
        "asreview_note": "notes",
    }


def test_asreview_csv__reads_labels() -> None:
    text = ",title,asreview_label\n0,A,1\n1,B,0\n2,C,\n3,D,-1\n"
    mapping = _csv_mapping(["", "title", "asreview_label"])

    result = parse_csv_text(text, mapping, settings=ASREVIEW.formats["csv"].settings)

    assert [row.record.labels[0].value for row in result.rows] == [
        "include",
        "exclude",
        "unlabeled",
        "unlabeled",
    ]


def test_asreview_ris__reads_labels_from_notes() -> None:
    profile = ASREVIEW.formats["ris"]
    mapping = suggest_ris_mapping(["TY", "N1", "TI"], profile.suggestions)

    result = parse_ris_text(_RIS, mapping, profile.settings)

    assert result.skipped == []
    assert [row.record.labels[0].value for row in result.rows] == [
        "include",
        "exclude",
        "unlabeled",
    ]


def _fixture(vendor: str, ext: str) -> Path:
    matches = sorted(_DATA_DIR.glob(f"asreview_{vendor}_small_*{ext}"))
    if not matches:
        pytest.skip(f"vendor fixture missing: asreview_{vendor}_small_*{ext}")
    return matches[0]


def _parse(path: Path, file_type: FileType) -> ParseResult:
    profile = ASREVIEW.formats[file_type]
    if file_type == "ris":
        mapping = suggest_ris_mapping(
            ["TY", "N1", "TI", "SP", "EP", "IS"],
            profile.suggestions,
            profile.row_defaults,
        )
        result = parse_ris_file(path, mapping, profile.settings)
    elif file_type == "excel":
        mapping = _csv_mapping(list(read_excel_headers(path).samples), file_type)
        result = parse_excel_file(path, mapping, None, profile.settings)
    else:
        delimiter = _TSV_DELIMITER if file_type == "tsv" else None
        headers = list(read_csv_headers(path, delimiter).samples)
        mapping = _csv_mapping(headers, file_type)
        result = parse_csv_file(path, mapping, delimiter, profile.settings)
    return apply_profile(result, profile, mapping)


_TYPES: dict[str, FileType] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".xlsx": "excel",
    ".ris": "ris",
}
_FIXTURES = [
    ("openalex", ".csv"),
    ("openalex", ".tsv"),
    ("openalex", ".xlsx"),
    ("openalex", ".ris"),
    ("pubmed", ".csv"),
    ("pubmed", ".tsv"),
    ("pubmed", ".xlsx"),
    ("scopus", ".csv"),
    ("scopus", ".tsv"),
    ("scopus", ".xlsx"),
    ("scopus", ".ris"),
]
_LABEL_COUNTS = {
    "openalex": {"include": 3, "exclude": 3, "unlabeled": 6},
    "pubmed": {"include": 2, "exclude": 2, "unlabeled": 8},
    "scopus": {"include": 4, "exclude": 2, "unlabeled": 4},
}


@pytest.mark.parametrize(("vendor", "ext"), _FIXTURES)
def test_asreview_fixture__detected_as_asreview(vendor: str, ext: str) -> None:
    path = _fixture(vendor, ext)

    file_type = detect_type(path)

    assert file_type == _TYPES[ext]
    assert detect_source(path, file_type) == "asreview"


@pytest.mark.parametrize(("vendor", "ext"), _FIXTURES)
def test_asreview_fixture__parses_labels_without_skips(vendor: str, ext: str) -> None:
    result = _parse(_fixture(vendor, ext), _TYPES[ext])

    labels = Counter(row.record.labels[0].value for row in result.rows)
    assert result.skipped == []
    assert labels == _LABEL_COUNTS[vendor]


@pytest.mark.parametrize("ext", [".csv", ".tsv", ".xlsx", ".ris"])
def test_asreview_fixture__reads_rispy_pages_and_issue(ext: str) -> None:
    result = _parse(_fixture("openalex", ext), _TYPES[ext])

    first = result.rows[0].record
    assert first.pages == "141-141"
    assert first.issue == "1"
