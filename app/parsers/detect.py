import csv
import re
from io import StringIO
from pathlib import Path

from app.parsers.common import decode_file
from app.parsers.profiles import PROFILES

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


def detect_source(path: Path, file_type: str) -> str | None:
    try:
        text = decode_file(path)
    except ValueError:
        return None
    for key, profile in PROFILES.items():
        format_profile = profile.formats.get(file_type)
        if format_profile is not None and format_profile.matches(text):
            return key
    return None
