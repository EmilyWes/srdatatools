import argparse
import logging
import multiprocessing
from logging.handlers import RotatingFileHandler
from pathlib import Path

from nicegui import native, ui

from app.db.session import default_db_path, run_migrations
from app.gui import home  # noqa: F401  (registers the "/" page)


def configure_logging(debug: bool, log_path: Path) -> None:
    file_handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8", delay=True
    )
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), file_handler],
        force=True,
    )


def main(argv: list[str] | None = None) -> None:
    # NiceGUI's native window runs in a spawned process that re-imports this
    # module; startup must only happen once, in the main process.
    if multiprocessing.current_process().name != "MainProcess":
        return

    parser = argparse.ArgumentParser(prog="srdatatools")
    parser.add_argument("--debug", action="store_true", help="log DEBUG messages")
    args = parser.parse_args(argv)

    configure_logging(args.debug, default_db_path().with_name("srdatatools.log"))
    run_migrations()
    ui.run(
        title="srdatatools",
        native=True,
        window_size=(1100, 700),
        reload=False,
        port=native.find_open_port(),
    )


if __name__ in {"__main__", "__mp_main__"}:
    multiprocessing.freeze_support()
    main()
