import csv
import re
from io import StringIO
from pathlib import Path

from app.parsers.common import decode_file

_RIS_FIRST_LINE = re.compile(r"^TY  -")
_NBIB_FIRST_LINE = re.compile(r"^PMID ?-")
_EXTENSION_TYPES = {".ris": "ris", ".nbib": "nbib", ".csv": "csv"}
_CSV_SAMPLE_SIZE = 2048


def _looks_like_csv(text: str) -> bool:
    try:
        dialect = csv.Sniffer().sniff(text[:_CSV_SAMPLE_SIZE], delimiters=",;\t")
        reader = csv.reader(StringIO(text), dialect=dialect)
        header = next(reader, [])
        first_row = next(reader, [])
    except csv.Error:
        return False
    return len(header) > 1 and len(first_row) == len(header)


def _type_from_content(text: str) -> str | None:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if _RIS_FIRST_LINE.match(first_line):
        return "ris"
    if _NBIB_FIRST_LINE.match(first_line):
        return "nbib"
    if _looks_like_csv(text):
        return "csv"
    return None


def detect_type(path: Path) -> str | None:
    try:
        file_type = _type_from_content(decode_file(path))
    except ValueError:
        file_type = None
    return file_type or _EXTENSION_TYPES.get(path.suffix.lower())
