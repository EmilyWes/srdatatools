from nicegui import native, ui

from app.gui import home  # noqa: F401  (registers the "/" page)


def main() -> None:
    ui.run(
        title="srdatatools",
        native=True,
        window_size=(480, 320),
        reload=False,
        port=native.find_open_port(),
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
