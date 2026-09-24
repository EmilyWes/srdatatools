from app.gui.layout import shell


def test_shell__builds_without_raising() -> None:
    shell()


def test_shell__creates_three_panes() -> None:
    panes = shell()

    assert panes.left.default_slot.children
    assert panes.middle.default_slot.children
    assert panes.right.default_slot.children
