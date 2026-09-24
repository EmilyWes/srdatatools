import pytest

import app.main


def test_main__runs_migrations_before_starting_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []

    monkeypatch.setattr(
        app.main, "run_migrations", lambda: call_order.append("run_migrations")
    )
    monkeypatch.setattr(
        app.main.ui, "run", lambda **kwargs: call_order.append("ui.run")
    )

    app.main.main()

    assert call_order == ["run_migrations", "ui.run"]
