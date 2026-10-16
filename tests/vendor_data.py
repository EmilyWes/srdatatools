from pathlib import Path
from typing import Literal, NoReturn

import pytest

# Vendor exports are licensed data, so they live only on the developer's machine
# (gitignored); tests that need them skip when they are missing.
_DATA_DIR = Path(__file__).parent / "data"
_VENDORS_DIR = _DATA_DIR / "vendors"

Size = Literal["small", "big"]


def _skip_missing(path: Path) -> NoReturn:
    pytest.skip(f"vendor fixture missing: {path.relative_to(_DATA_DIR)}")


def vendor_file(size: Size, vendor: str, name: str) -> Path:
    path = _VENDORS_DIR / size / vendor / name
    if not path.is_file():
        _skip_missing(path)
    return path


def vendor_files(size: Size, vendor: str) -> list[Path]:
    folder = _VENDORS_DIR / size / vendor
    files = sorted(p for p in folder.glob("*") if p.is_file())
    if not files:
        _skip_missing(folder)
    return files
