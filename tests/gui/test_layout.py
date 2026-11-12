from nicegui import ui

from app.gui.layout import shell


def test_shell__builds_without_raising() -> None:
    shell()


def test_shell__creates_three_panes() -> None:
    panes = shell()

    row = panes.middle.parent_slot
    left_column = panes.left.parent_slot
    assert row is not None and left_column is not None
    assert row.children[-3:] == [left_column.parent, panes.middle, panes.right]


def test_shell__shows_the_app_name_above_the_left_pane() -> None:
    panes = shell()

    left_column = panes.left.parent_slot
    assert left_column is not None
    brand = left_column.children[0]
    assert "srdatatools" in [
        e.text for e in brand.descendants() if isinstance(e, ui.label)
    ]


def test_shell__only_the_middle_pane_scrolls() -> None:
    panes = shell()

    assert "overflow-y-auto" in panes.middle.classes
    assert "overflow-y-auto" not in panes.left.classes
    assert "overflow-y-auto" not in panes.right.classes
