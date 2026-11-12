import csv
import re
from io import StringIO
from pathlib import Path

from app.parsers.common import FileType, decode_prefix
from app.parsers.csv_ import sniff_dialect
from app.parsers.excel import read_excel_headers
from app.parsers.profiles import PROFILES

_RIS_START = re.compile(r"^TY  -")
_NBIB_START = re.compile(r"^PMID ?-")
# Room for lines before the first record (ASReview numbers its RIS records, "1."),
# yet a tabular file with tag-like text deep in a cell isn't taken for RIS/NBIB.
_START_LINES = 10
# Searched, not matched on the first line: exports may start with a free-text header.
_BIBTEX_ENTRY = re.compile(
    r"^[ \t]*@(?!(?:comment|string|preamble)\b)[A-Za-z]+[ \t]*[{(]",
    re.MULTILINE | re.IGNORECASE,
)
_EXTENSION_TYPES: dict[str, FileType] = {
    ".ris": "ris",
    ".nbib": "nbib",
    ".csv": "csv",
    ".tsv": "tsv",
    ".bib": "bibtex",
}
_DETECT_PREFIX_SIZE = 4 * 1024 * 1024


def _sniff_tabular(text: str) -> str | None:
    dialect = sniff_dialect(text)
    if dialect is None:
        return None
    try:
        reader = csv.reader(StringIO(text), dialect=dialect)
        header = next(reader, [])
        first_row = next(reader, [])
    except csv.Error:
        return None
    if len(header) > 1 and len(first_row) == len(header):
        return dialect.delimiter
    return None


def _type_from_content(text: str) -> FileType | None:
    lines = [line for line in text.splitlines() if line.strip()][:_START_LINES]
    for line in lines:
        if _RIS_START.match(line):
            return "ris"
        if _NBIB_START.match(line):
            return "nbib"
    if _BIBTEX_ENTRY.search(text):
        return "bibtex"
    delimiter = _sniff_tabular(text)
    if delimiter is None:
        return None
    return "tsv" if delimiter == "\t" else "csv"


def detect_type(path: Path) -> FileType | None:
    # A workbook is a zip archive, so its content can't be sniffed as text.
    if path.suffix.lower() == ".xlsx":
        return "excel"
    try:
        file_type = _type_from_content(decode_prefix(path, _DETECT_PREFIX_SIZE))
    except ValueError:
        file_type = None
    return file_type or _EXTENSION_TYPES.get(path.suffix.lower())


def _detect_text(path: Path, file_type: FileType) -> str:
    """A workbook can't be read as text, so profiles see its tab-joined header row."""
    if file_type == "excel":
        return "	".join(read_excel_headers(path).samples)
    return decode_prefix(path, _DETECT_PREFIX_SIZE)


def detect_source(path: Path, file_type: FileType) -> str | None:
    try:
        text = _detect_text(path, file_type)
    except ValueError:
        return None
    for key, profile in PROFILES.items():
        format_profile = profile.formats.get(file_type)
        if format_profile is not None and format_profile.matches(text):
            return key
    return None
