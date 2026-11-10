from app.gui.layout import shell


def test_shell__builds_without_raising() -> None:
    shell()


def test_shell__creates_three_panes() -> None:
    panes = shell()

    row = panes.left.parent_slot
    assert row is not None
    assert row.children[-3:] == [panes.left, panes.middle, panes.right]
