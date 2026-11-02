"""Entry point: `pythonw -m capture_compressor` (tray) or `--headless` / `--once`."""

from __future__ import annotations

import argparse
import logging
import time

from .engine import CompressionEngine
from .logging_setup import configure_logging
from .settings import Settings

logger = logging.getLogger("capture_compressor")
WAIT_STEP_SECONDS = 1


def parse_command_line() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="capture_compressor")
    parser.add_argument("--folder", help="watch this folder instead of the saved setting")
    parser.add_argument("--headless", action="store_true", help="no tray icon, log to the console")
    parser.add_argument("--once", action="store_true",
                        help="compress what is in the folder now, then exit")
    return parser.parse_args()


def main() -> None:
    command_line = parse_command_line()
    headless = command_line.headless or command_line.once
    log_file = configure_logging(also_to_console=headless)
    settings, settings_existed = Settings.load()
    if command_line.folder:
        settings.watch_folder = command_line.folder
    logger.info("Starting (log: %s)", log_file)

    if headless:
        run_headless(settings, exit_when_idle=command_line.once)
    else:
        from .tray import run_tray  # imports tkinter and pystray only when needed
        run_tray(settings, first_run=not settings_existed)


def run_headless(settings: Settings, exit_when_idle: bool) -> None:
    engine = CompressionEngine(settings, notify=lambda message: logger.warning("NOTIFY: %s", message))
    engine.start()
    try:
        time.sleep(WAIT_STEP_SECONDS)
        while not (exit_when_idle and _nothing_left_to_do(engine)):
            time.sleep(WAIT_STEP_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        logger.info("Stopped")


def _nothing_left_to_do(engine: CompressionEngine) -> bool:
    return engine.is_idle() or not engine.active_encoder


if __name__ == "__main__":
    main()
