# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a one-file srdatatools executable.

Run from the repo root: `python -m PyInstaller packaging/pyinstaller.spec`

NiceGUI ships its static/vendor web assets (Vue, Quasar, etc.) as package
data that PyInstaller's import analysis can't discover on its own, so they
are added explicitly below (mirrors NiceGUI's own `nicegui-pack` helper).
Alembic reads alembic.ini and the migration scripts as files at startup, so
they are bundled as data too (see app.db.session.project_root).
pywebview bundles its own PyInstaller hook, so it needs no extra data here.
The About view reads LICENSE, THIRD_PARTY_LICENSES.txt (regenerate it with
packaging/third_party_licenses.py before building) and srdatatools' own
package metadata, so those are bundled too.
"""

from pathlib import Path

import nicegui
from PyInstaller.utils.hooks import copy_metadata

REPO_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821  (injected by PyInstaller)
NICEGUI_ROOT = Path(nicegui.__file__).parent

a = Analysis(  # noqa: F821  (injected by PyInstaller)
    [str(REPO_ROOT / "app" / "main.py")],
    pathex=[str(REPO_ROOT)],
    datas=[
        (str(NICEGUI_ROOT), "nicegui"),
        (str(REPO_ROOT / "alembic.ini"), "."),
        (str(REPO_ROOT / "app" / "db" / "migrations"), "app/db/migrations"),
        (str(REPO_ROOT / "LICENSE"), "."),
        (str(REPO_ROOT / "THIRD_PARTY_LICENSES.txt"), "."),
        *copy_metadata("srdatatools"),
    ],
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
