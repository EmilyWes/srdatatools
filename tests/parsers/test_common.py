from pathlib import Path

import pytest

from app.parsers.common import FileSummary, decode_prefix, merge_summaries


def _write(tmp_path: Path, raw_bytes: bytes) -> Path:
    path = tmp_path / "export.txt"
    path.write_bytes(raw_bytes)
    return path


def test_decode_prefix__returns_only_first_bytes(tmp_path: Path) -> None:
    path = _write(tmp_path, b"TY  - JOUR\nTI  - Title\n")

    assert decode_prefix(path, 10) == "TY  - JOUR"


def test_decode_prefix__drops_character_cut_at_boundary(tmp_path: Path) -> None:
    path = _write(tmp_path, "café au lait".encode())

    assert decode_prefix(path, 4) == "caf"  # "é" is two bytes, only one fits


def test_decode_prefix__strips_utf8_bom(tmp_path: Path) -> None:
    path = _write(tmp_path, "﻿Title,Year\n".encode())

    assert decode_prefix(path, 100) == "Title,Year\n"


def test_decode_prefix__falls_back_to_cp1252(tmp_path: Path) -> None:
    path = _write(tmp_path, "Title\nCaf\xe9\n".encode("cp1252"))

    assert decode_prefix(path, 100) == "Title\nCafé\n"


def test_decode_prefix__undecodable_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, b"\x81")  # undefined in both utf-8-sig and cp1252

    with pytest.raises(ValueError, match="could not decode"):
        decode_prefix(path, 100)


def test_merge_summaries__single_summary_unchanged() -> None:
    summary = FileSummary({"TI": "A title"}, {"TI": 1}, 1)

    assert merge_summaries([summary]) == summary


def test_merge_summaries__unions_keys_in_first_seen_order() -> None:
    first = FileSummary({"TI": "A", "AU": "Smith"}, {"TI": 1, "AU": 1}, 1)
    second = FileSummary({"AB": "Text", "TI": "B"}, {"AB": 1, "TI": 1}, 1)

    merged = merge_summaries([first, second])

    assert list(merged.samples) == ["TI", "AU", "AB"]
    assert list(merged.filled) == ["TI", "AU", "AB"]


def test_merge_summaries__sums_filled_and_total_rows() -> None:
    first = FileSummary({"TI": "A", "AU": "Smith"}, {"TI": 3, "AU": 1}, 4)
    second = FileSummary({"TI": "B"}, {"TI": 2}, 5)

    merged = merge_summaries([first, second])

    assert merged.filled == {"TI": 5, "AU": 1}
    assert merged.total_rows == 9


def test_merge_summaries__takes_first_non_empty_sample() -> None:
    first = FileSummary({"TI": "", "AU": "Smith"}, {"TI": 0, "AU": 1}, 1)
    second = FileSummary({"TI": "B", "AU": "Jones"}, {"TI": 1, "AU": 1}, 1)

    merged = merge_summaries([first, second])

    assert merged.samples == {"TI": "B", "AU": "Smith"}
