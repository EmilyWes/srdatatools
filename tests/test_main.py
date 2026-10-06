import logging
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.main


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers.clear()
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _stub_startup(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[str, object]]
) -> None:
    monkeypatch.setattr(
        app.main,
        "configure_logging",
        lambda debug, log_path: calls.append(("configure_logging", debug)),
    )
    monkeypatch.setattr(
        app.main, "run_migrations", lambda: calls.append(("run_migrations", None))
    )
    monkeypatch.setattr(
        app.main.ui, "run", lambda **kwargs: calls.append(("ui.run", None))
    )


def test_main__configures_logging_then_migrates_then_starts_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    _stub_startup(monkeypatch, calls)

    app.main.main([])

    assert calls == [
        ("configure_logging", False),
        ("run_migrations", None),
        ("ui.run", None),
    ]


def test_main__debug_flag_enables_debug_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    _stub_startup(monkeypatch, calls)

    app.main.main(["--debug"])

    assert calls[0] == ("configure_logging", True)


def test_main__skips_startup_outside_main_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    _stub_startup(monkeypatch, calls)
    monkeypatch.setattr(
        app.main.multiprocessing,
        "current_process",
        lambda: SimpleNamespace(name="SpawnProcess-1"),
    )

    app.main.main([])

    assert calls == []


def test_configure_logging__defaults_to_warning_and_writes_file(
    root_logger: logging.Logger, tmp_path: Path
) -> None:
    log_path = tmp_path / "srdatatools.log"

    app.main.configure_logging(debug=False, log_path=log_path)
    logging.getLogger("app.test").warning("something odd")
    logging.getLogger("app.test").info("routine detail")

    assert root_logger.level == logging.WARNING
    contents = log_path.read_text(encoding="utf-8")
    assert "something odd" in contents
    assert "routine detail" not in contents


def test_configure_logging__debug_enables_debug_level(
    root_logger: logging.Logger, tmp_path: Path
) -> None:
    app.main.configure_logging(debug=True, log_path=tmp_path / "srdatatools.log")

    assert root_logger.level == logging.DEBUG
