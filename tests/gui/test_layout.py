from app.gui.layout import shell


def test_shell__builds_without_raising() -> None:
    shell()


def test_shell__creates_three_panes() -> None:
    panes = shell()

    row = panes.left.parent_slot
    assert row is not None
    assert row.children[-3:] == [panes.left, panes.middle, panes.right]


def test_shell__only_the_middle_pane_scrolls() -> None:
    panes = shell()

    assert "overflow-y-auto" in panes.middle.classes
    assert "overflow-y-auto" not in panes.left.classes
    assert "overflow-y-auto" not in panes.right.classes
