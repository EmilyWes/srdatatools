import datetime

from nicegui import ui
from nicegui.element import Element

from app.db.models import ActivityLog
from app.gui.action_panel import render_right_panel
from app.gui.layout import shell


def _row_buttons(right: Element) -> list[list[ui.button]]:
    buttons_column = right.default_slot.children[0]
    return [
        [child for child in row.default_slot.children if isinstance(child, ui.button)]
        for row in buttons_column.default_slot.children
    ]


def _click(element: ui.button) -> None:
    click_listener = next(iter(element._event_listeners.values()))
    assert click_listener.handler is not None
    click_listener.handler(None)


def _entry(timestamp: datetime.datetime, message: str) -> ActivityLog:
    return ActivityLog(timestamp=timestamp, action_type="import", message=message)


def test_render_right_panel__builds_without_raising() -> None:
    panes = shell()

    render_right_panel(panes.right, panes.middle)


def test_render_right_panel__action_buttons_in_order_and_disabled() -> None:
    panes = shell()

    render_right_panel(panes.right, panes.middle)

    action_buttons = [buttons[0] for buttons in _row_buttons(panes.right)]
    assert [button.text for button in action_buttons] == [
        "Dedup",
        "Enrich",
        "Snowball",
        "Export",
    ]
    assert not any(button.enabled for button in action_buttons)


def test_render_right_panel__one_settings_gear_per_action() -> None:
    panes = shell()

    render_right_panel(panes.right, panes.middle)

    gears = [buttons[1] for buttons in _row_buttons(panes.right)]
    assert [gear.props["icon"] for gear in gears] == ["settings"] * 4


def test_render_right_panel__gear_shows_settings_in_middle_and_calls_back() -> None:
    panes = shell()
    calls: list[None] = []
    render_right_panel(
        panes.right, panes.middle, on_settings=lambda: calls.append(None)
    )

    enrich_gear = _row_buttons(panes.right)[1][1]
    _click(enrich_gear)

    assert calls == [None]
    middle_children = panes.middle.default_slot.children
    assert len(middle_children) == 1
    labels = middle_children[0].default_slot.children
    assert labels[0].text == "Enrich settings"  # type: ignore[attr-defined]


def test_render_right_panel__log_textbox_is_readonly_and_empty() -> None:
    panes = shell()

    actions = render_right_panel(panes.right, panes.middle)

    assert "readonly" in actions.log.props
    assert actions.log.value == ""


def test_action_panel__show_log_lists_entries_one_per_line() -> None:
    panes = shell()
    actions = render_right_panel(panes.right, panes.middle)

    actions.show_log(
        [
            _entry(datetime.datetime(2026, 1, 1, 9, 5), "Imported 5 records"),
            _entry(datetime.datetime(2026, 1, 2, 14, 30), "Imported 10 records"),
        ]
    )

    assert actions.log.value == (
        "2026-01-01 09:05  Imported 5 records\n2026-01-02 14:30  Imported 10 records"
    )


def test_action_panel__show_log_empty_entries_clears_textbox() -> None:
    panes = shell()
    actions = render_right_panel(panes.right, panes.middle)
    actions.show_log([_entry(datetime.datetime(2026, 1, 1), "Imported 5 records")])

    actions.show_log([])

    assert actions.log.value == ""


def test_action_panel__show_log_schedules_scroll_to_bottom() -> None:
    panes = shell()
    actions = render_right_panel(panes.right, panes.middle)

    actions.show_log([])

    assert any(
        isinstance(child, ui.timer) for child in panes.right.default_slot.children
    )
