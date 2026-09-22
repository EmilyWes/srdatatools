# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a one-file srdatatools executable.

Run from the repo root: `python -m PyInstaller packaging/pyinstaller.spec`

NiceGUI ships its static/vendor web assets (Vue, Quasar, etc.) as package
data that PyInstaller's import analysis can't discover on its own, so they
are added explicitly below (mirrors NiceGUI's own `nicegui-pack` helper).
pywebview bundles its own PyInstaller hook, so it needs no extra data here.
"""

from pathlib import Path

import nicegui

REPO_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821  (injected by PyInstaller)
NICEGUI_ROOT = Path(nicegui.__file__).parent

a = Analysis(  # noqa: F821  (injected by PyInstaller)
    [str(REPO_ROOT / "app" / "main.py")],
    pathex=[str(REPO_ROOT)],
    datas=[(str(NICEGUI_ROOT), "nicegui")],
)
pyz = PYZ(a.pure)  # noqa: F821  (injected by PyInstaller)

exe = EXE(  # noqa: F821  (injected by PyInstaller)
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="srdatatools",
    console=False,
)
