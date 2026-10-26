from pathlib import Path

import pytest

from app.parsers.common import decode_prefix


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
