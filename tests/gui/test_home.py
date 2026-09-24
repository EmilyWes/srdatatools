import pytest
from sqlalchemy import create_engine

import app.gui.home as home_module
import app.main
from app.db.models import Base
from app.gui.home import home


@pytest.fixture(autouse=True)
def _in_memory_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(home_module, "_engine", engine)


def test_home__builds_without_raising() -> None:
    home()


def test_main__importable_without_launching_ui_run() -> None:
    assert callable(app.main.main)
