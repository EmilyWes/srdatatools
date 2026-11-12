import importlib.util
from pathlib import Path
from types import ModuleType

_SCRIPT = (
    Path(__file__).resolve().parent.parent / "packaging" / "third_party_licenses.py"
)


def _script() -> ModuleType:
    # Loaded by path: the repo's packaging/ folder isn't a package and shares its
    # name with the `packaging` library the script imports.
    spec = importlib.util.spec_from_file_location("third_party_licenses", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _closure_names() -> set[str]:
    return {dist.metadata["Name"].lower() for dist in _script().runtime_closure()}


def test_runtime_closure__includes_transitive_dependencies() -> None:
    assert {"nicegui", "starlette"} <= _closure_names()


def test_runtime_closure__excludes_dev_and_build_extras() -> None:
    assert not {"pytest", "black", "mypy", "pyinstaller"} & _closure_names()


def test_render__has_python_packages_and_web_assets() -> None:
    script = _script()

    text = script.render(script.runtime_closure())

    assert text.startswith("srdatatools bundles the following third-party software.")
    assert "\nPython 3." in text
    assert "\nnicegui " in text
    assert "Apache ECharts (Apache-2.0)" in text


def test_render_summary__one_line_per_component_without_urls() -> None:
    script = _script()
    closure = script.runtime_closure()

    lines = script.render_summary(closure).splitlines()

    assert lines[0].startswith("Python 3.")
    assert len(lines) == 1 + len(closure) + len(script.WEB_ASSETS)
    assert "Apache ECharts (Apache-2.0)" in lines
    assert not any("://" in line for line in lines)
