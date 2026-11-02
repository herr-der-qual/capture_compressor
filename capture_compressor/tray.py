"""Tray icon and the glue between pystray, tkinter and the engine.

tkinter owns the main thread; pystray runs its own message loop in a second
thread. Menu clicks are handed over to the tkinter thread through a queue.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import tkinter
from tkinter import messagebox
from typing import Callable

import pystray
from PIL import ImageTk

from . import autostart, single_instance, status
from .engine import CompressionEngine
from .logging_setup import log_file_path
from .settings import Settings
from .settings_window import SettingsWindow
from .status import Status
from .tray_icon_image import draw_tray_icon

logger = logging.getLogger(__name__)

APPLICATION_TITLE = "Capture Compressor"
MAXIMUM_TOOLTIP_LENGTH = 127
MAXIMUM_NOTIFICATION_LENGTH = 250
MAXIMUM_MENU_STATUS_LENGTH = 60
QUEUE_CHECK_MILLISECONDS = 100
PROCESS_DPI_AWARE = 1


class TrayApplication:
    def __init__(self, settings: Settings, first_run: bool) -> None:
        self.settings = settings
        self.first_run = first_run
        self.interface_calls: queue.Queue[Callable[[], None]] = queue.Queue()
        self.root = tkinter.Tk()
        self.root.withdraw()
        self._window_icon = ImageTk.PhotoImage(draw_tray_icon(status.IDLE))
        self.root.iconphoto(True, self._window_icon)  # also used by the Settings window
        self.settings_window: SettingsWindow | None = None
        self.engine = CompressionEngine(
            settings, on_status_change=self._show_status, notify=self._notify
        )
        self.icon = pystray.Icon(
            "CaptureCompressor",
            draw_tray_icon(status.IDLE),
            f"{APPLICATION_TITLE} - starting",
            menu=self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: self.engine.status.describe()[:MAXIMUM_MENU_STATUS_LENGTH],
                None, enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings...", self._on_interface_thread(self.open_settings), default=True),
            pystray.MenuItem(
                lambda item: "Resume" if self.engine.paused else "Pause",
                lambda: self.engine.set_paused(not self.engine.paused),
            ),
            pystray.MenuItem("Open folder", lambda: _open_with_windows(self.settings.watch_folder)),
            pystray.MenuItem("Open log", lambda: _open_with_windows(str(log_file_path()))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_interface_thread(self.exit)),
        )

    def run(self) -> None:
        if self.first_run:
            self.settings.save()
        self._synchronize_autostart()
        threading.Thread(target=self.icon.run, name="tray", daemon=True).start()
        # The encoder test takes a moment; the tray icon should not wait for it.
        threading.Thread(target=self.engine.start, name="engine-start", daemon=True).start()
        self.root.after(QUEUE_CHECK_MILLISECONDS, self._run_queued_interface_calls)
        self.root.mainloop()

    def _synchronize_autostart(self) -> bool:
        try:
            autostart.synchronize(self.settings.start_with_windows)
            return True
        except OSError:
            logger.exception("Could not update the autostart entry")
            return False

    # ---- thread hand-over ---------------------------------------------------

    def _on_interface_thread(self, action: Callable[[], None]) -> Callable[..., None]:
        """Wrap a menu callback so it runs on the tkinter thread."""
        return lambda *menu_arguments: self.interface_calls.put(action)

    def _run_queued_interface_calls(self) -> None:
        while True:
            try:
                action = self.interface_calls.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception:
                logger.exception("Interface action failed")
        self.root.after(QUEUE_CHECK_MILLISECONDS, self._run_queued_interface_calls)

    # ---- engine callbacks (worker thread) ----------------------------------

    def _show_status(self, new_status: Status) -> None:
        self.icon.icon = draw_tray_icon(new_status.state)
        self.icon.title = f"{APPLICATION_TITLE} - {new_status.describe()}"[:MAXIMUM_TOOLTIP_LENGTH]
        self.icon.update_menu()

    def _notify(self, message: str) -> None:
        logger.info("Notification: %s", message)
        try:
            self.icon.notify(message[:MAXIMUM_NOTIFICATION_LENGTH], APPLICATION_TITLE)
        except Exception:
            logger.exception("Could not show a notification")

    # ---- actions (tkinter thread) -------------------------------------------

    def open_settings(self) -> None:
        if self.settings_window and self.settings_window.is_open():
            self.settings_window.bring_to_front()
            return
        self.settings_window = SettingsWindow(
            self.root, self.settings, self.engine.active_encoder, self._save_settings
        )

    def _save_settings(self, updated: Settings) -> None:
        updated.save()
        self.settings = updated
        logger.info("Settings saved: %s", updated)
        if not self._synchronize_autostart():
            messagebox.showerror(APPLICATION_TITLE, "Could not change autostart, see the log.")
        # Testing a new encoder takes a moment; keep the interface responsive.
        threading.Thread(target=self.engine.apply_settings, args=(updated,), daemon=True).start()

    def exit(self) -> None:
        logger.info("Exiting")
        self.icon.stop()
        self.engine.stop()
        self.root.quit()


def _open_with_windows(path: str) -> None:
    try:
        os.startfile(path)
    except OSError:
        logger.exception("Could not open %s", path)


def _make_process_dpi_aware() -> None:
    """Without this tkinter looks blurry on scaled (HiDPI) screens."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_DPI_AWARE)
    except (AttributeError, OSError):
        pass


def run_tray(settings: Settings, first_run: bool) -> None:
    _make_process_dpi_aware()
    if single_instance.another_instance_is_running():
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showinfo(APPLICATION_TITLE, "Capture Compressor is already running (see the tray).")
        return
    TrayApplication(settings, first_run).run()
