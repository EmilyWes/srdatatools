from pathlib import Path
from typing import Literal, NoReturn

import pytest

# Vendor exports are licensed data, so they live only on the developer's machine
# (gitignored); tests that need them skip when they are missing. Files are named
# <vendor>_<size>_<date>.<ext>; the date is globbed so refreshed exports need no
# test changes.
_DATA_DIR = Path(__file__).parent / "data"

Size = Literal["small", "big"]


def _skip_missing(pattern: str) -> NoReturn:
    pytest.skip(f"vendor fixture missing: {pattern}")


def vendor_file(vendor: str, size: Size, ext: str) -> Path:
    pattern = f"{vendor}/{vendor}_{size}_*{ext}"
    matches = sorted(_DATA_DIR.glob(pattern))
    if not matches:
        _skip_missing(pattern)
    if len(matches) > 1:
        raise ValueError(f"multiple vendor fixtures match {pattern}: {matches}")
    return matches[0]


def vendor_files(vendor: str, size: Size) -> list[Path]:
    pattern = f"{vendor}/{vendor}_{size}_*"
    files = sorted(p for p in _DATA_DIR.glob(pattern) if p.is_file())
    if not files:
        _skip_missing(pattern)
    return files
