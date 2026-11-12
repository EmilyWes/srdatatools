from nicegui import ui
from nicegui.element import Element

from app.db.session import project_root
from app.gui.about import (
    HELP_PLACEHOLDER,
    REPOSITORY_URL,
    render_about_view,
    render_help_view,
)
from app.gui.layout import shell


def _texts(middle: Element) -> list[str]:
    return [e.text for e in middle.descendants() if isinstance(e, ui.label)]


def test_render_about_view__shows_version_link_and_both_licenses() -> None:
    panes = shell()

    render_about_view(panes.middle)

    texts = _texts(panes.middle)
    assert "srdatatools" in texts
    assert any(text.startswith("Version ") for text in texts)
    [link] = [e for e in panes.middle.descendants() if isinstance(e, ui.link)]
    assert link.props["href"] == REPOSITORY_URL
    root = project_root()
    for name in ("LICENSE", "THIRD_PARTY_SUMMARY.txt", "THIRD_PARTY_LICENSES.txt"):
        assert (root / name).read_text(encoding="utf-8") in texts


def test_render_about_view__license_texts_start_collapsed() -> None:
    panes = shell()

    render_about_view(panes.middle)

    expansions = [e for e in panes.middle.descendants() if isinstance(e, ui.expansion)]
    assert [e.props["label"] for e in expansions] == ["License", "Full license texts"]
    assert not any(e.value for e in expansions)


def test_render_help_view__shows_placeholder() -> None:
    panes = shell()

    render_help_view(panes.middle)

    assert _texts(panes.middle) == ["Help", HELP_PLACEHOLDER]
