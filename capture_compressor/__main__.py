"""Entry point: `pythonw -m capture_compressor` (tray) or `--headless` / `--once`."""

from __future__ import annotations

import argparse
import logging
import time

from .config import Settings, setup_logging
from .engine import Engine

log = logging.getLogger("capture_compressor")


def main() -> None:
    parser = argparse.ArgumentParser(prog="capture_compressor")
    parser.add_argument("--folder", help="watch this folder instead of the saved setting")
    parser.add_argument("--headless", action="store_true", help="no tray icon, log to console")
    parser.add_argument("--once", action="store_true",
                        help="compress what is in the folder now, then exit")
    args = parser.parse_args()

    headless = args.headless or args.once
    log_path = setup_logging(also_console=headless)
    settings, existed = Settings.load()
    if args.folder:
        settings.watch_folder = args.folder
    log.info("Starting (log: %s)", log_path)

    if not headless:
        from .tray import run_tray
        run_tray(settings, first_run=not existed)
        return

    engine = Engine(settings, on_notify=lambda m: log.warning("NOTIFY: %s", m))
    engine.start()
    try:
        if args.once:
            time.sleep(1)
            while engine.encoder and not engine.is_idle():
                time.sleep(1)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        log.info("Stopped")


if __name__ == "__main__":
    main()
