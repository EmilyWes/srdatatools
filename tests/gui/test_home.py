import app.main
from app.gui.home import home


def test_home__builds_without_raising() -> None:
    home()


def test_main__importable_without_launching_ui_run() -> None:
    assert callable(app.main.main)
