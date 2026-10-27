import codecs
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.models.record import Record

_FILE_ENCODINGS = ("utf-8-sig", "cp1252")


@dataclass
class ParsedRow:
    record: Record
    raw_fields: dict[str, str]


@dataclass
class SkippedRow:
    row_number: int
    reason: str


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    skipped: list[SkippedRow]


@dataclass
class FileSummary:
    samples: dict[str, str]
    filled: dict[str, int]
    total_rows: int


class SummaryBuilder:
    """Tallies, per key, the first non-empty value and in how many records it is set."""

    def __init__(self, keys: Iterable[str] = ()) -> None:
        self._samples = dict.fromkeys(keys, "")
        self._filled = dict.fromkeys(keys, 0)
        self._total_rows = 0
        self._record_filled: set[str] = set()
        self._in_record = False

    def add(self, key: str, value: str) -> None:
        self._samples.setdefault(key, "")
        self._filled.setdefault(key, 0)
        self._in_record = True
        stripped = value.strip()
        if stripped:
            self._record_filled.add(key)
            if not self._samples[key]:
                self._samples[key] = stripped

    def end_record(self) -> None:
        if not self._in_record:
            return
        for key in self._record_filled:
            self._filled[key] += 1
        self._total_rows += 1
        self._record_filled = set()
        self._in_record = False

    def build(self) -> FileSummary:
        self.end_record()
        return FileSummary(self._samples, self._filled, self._total_rows)


def merge_summaries(summaries: list[FileSummary]) -> FileSummary:
    samples: dict[str, str] = {}
    filled: dict[str, int] = {}
    for summary in summaries:
        for key, sample in summary.samples.items():
            if not samples.get(key):
                samples[key] = sample
        for key, count in summary.filled.items():
            filled[key] = filled.get(key, 0) + count
    total_rows = sum(summary.total_rows for summary in summaries)
    return FileSummary(samples, filled, total_rows)


def decode_file(path: Path) -> str:
    raw_bytes = path.read_bytes()
    for encoding in _FILE_ENCODINGS:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path} using any of {_FILE_ENCODINGS}")


def decode_prefix(path: Path, size: int) -> str:
    with path.open("rb") as file:
        raw_bytes = file.read(size)
    for encoding in _FILE_ENCODINGS:
        # final=False: a character cut off at the end is dropped instead of raising.
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            return decoder.decode(raw_bytes, final=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path} using any of {_FILE_ENCODINGS}")
