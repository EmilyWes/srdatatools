"""Write THIRD_PARTY_LICENSES.txt for the packages a frozen build ships.

Run from the repo root, in the environment the executable is built from:
`python packaging/third_party_licenses.py`

The dependency closure is evaluated for the current platform, so rerun this on
each platform before building there.
"""

import re
import sys
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT_PACKAGE = "srdatatools"
OUTPUT = Path(__file__).resolve().parent.parent / "THIRD_PARTY_LICENSES.txt"
_LICENSE_FILE = re.compile(r"licen[cs]e|copying|notice", re.IGNORECASE)
_SEPARATOR = "=" * 79

# nicegui vendors these web libraries and fonts as files without Python package
# metadata, so they are listed by hand. Check this list when upgrading nicegui.
WEB_ASSETS: list[tuple[str, str, str]] = [
    ("Vue", "MIT", "https://github.com/vuejs/core/blob/main/LICENSE"),
    ("Quasar", "MIT", "https://github.com/quasarframework/quasar/blob/dev/LICENSE"),
    ("Tailwind CSS", "MIT", "https://github.com/tailwindlabs/tailwindcss"),
    ("UnoCSS", "MIT", "https://github.com/unocss/unocss/blob/main/LICENSE"),
    ("Socket.IO client", "MIT", "https://github.com/socketio/socket.io"),
    (
        "DOMPurify",
        "MPL-2.0 OR Apache-2.0",
        "https://github.com/cure53/DOMPurify/blob/main/LICENSE",
    ),
    ("Immutable.js", "MIT", "https://github.com/immutable-js/immutable-js"),
    ("Dart Sass", "MIT", "https://github.com/sass/dart-sass/blob/main/LICENSE"),
    ("Apache ECharts", "Apache-2.0", "https://github.com/apache/echarts"),
    ("AG Grid Community", "MIT", "https://github.com/ag-grid/ag-grid"),
    ("CodeMirror", "MIT", "https://github.com/codemirror/dev/blob/main/LICENSE"),
    ("Mermaid", "MIT", "https://github.com/mermaid-js/mermaid/blob/develop/LICENSE"),
    ("Plotly.js", "MIT", "https://github.com/plotly/plotly.js/blob/master/LICENSE"),
    ("three.js", "MIT", "https://github.com/mrdoob/three.js/blob/dev/LICENSE"),
    ("Leaflet", "BSD-2-Clause", "https://github.com/Leaflet/Leaflet/blob/main/LICENSE"),
    ("xterm.js", "MIT", "https://github.com/xtermjs/xterm.js/blob/master/LICENSE"),
    ("nipplejs", "MIT", "https://github.com/yoannmoinet/nipplejs"),
    ("vanilla-jsoneditor", "ISC", "https://github.com/josdejong/svelte-jsoneditor"),
    ("SortableJS", "MIT", "https://github.com/SortableJS/Sortable"),
    ("anywidget", "MIT", "https://github.com/manzt/anywidget"),
    ("Roboto font", "OFL-1.1", "https://github.com/googlefonts/roboto-3-classic"),
    (
        "Material Icons / Material Symbols fonts",
        "Apache-2.0",
        "https://github.com/google/material-design-icons/blob/master/LICENSE",
    ),
]


def runtime_closure(root: str = ROOT_PACKAGE) -> list[Distribution]:
    """`root`'s dependencies and theirs, without extras, for this platform."""
    seen: dict[str, Distribution] = {}
    pending = [root]
    while pending:
        dist = distribution(pending.pop())
        for spec in dist.requires or []:
            requirement = Requirement(spec)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            name = canonicalize_name(requirement.name)
            if name in seen:
                continue
            try:
                seen[name] = distribution(name)
            except PackageNotFoundError:
                continue
            pending.append(name)
    return sorted(seen.values(), key=lambda d: canonicalize_name(d.metadata["Name"]))


def license_name(dist: Distribution) -> str:
    metadata = dist.metadata
    if expression := metadata.get("License-Expression"):
        return expression
    # Some packages put the whole license text in License.
    if (text := metadata.get("License")) and "\n" not in text.strip():
        return text.strip()
    classifiers = [
        c.split(" :: ")[-1]
        for c in metadata.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    return ", ".join(classifiers) or "see license text"


def license_texts(dist: Distribution) -> list[str]:
    return [
        Path(file.locate()).read_text(encoding="utf-8", errors="replace").strip()
        for file in dist.files or []
        if ".dist-info" in str(file) and _LICENSE_FILE.search(file.name)
    ]


def _python_license() -> str:
    base = Path(sys.base_prefix)
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for path in (base / "LICENSE.txt", base / "lib" / version / "LICENSE.txt"):
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    return "See https://docs.python.org/3/license.html"


def _section(title: str, body: str) -> str:
    return f"{_SEPARATOR}\n{title}\n{_SEPARATOR}\n\n{body}\n"


def render() -> str:
    version = ".".join(map(str, sys.version_info[:3]))
    sections = [
        "srdatatools bundles the following third-party software.\n",
        _section(f"Python {version} (PSF-2.0)", _python_license()),
    ]
    for dist in runtime_closure():
        title = f"{dist.metadata['Name']} {dist.version} ({license_name(dist)})"
        texts = license_texts(dist) or ["No license file included in the package."]
        sections.append(_section(title, "\n\n".join(texts)))
    assets = "\n".join(f"{name} ({spdx}): {url}" for name, spdx, url in WEB_ASSETS)
    sections.append(_section("Web libraries and fonts bundled with NiceGUI", assets))
    return "\n".join(sections)


if __name__ == "__main__":
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}")
