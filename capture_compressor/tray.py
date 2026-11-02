"""Tray icon and the glue between pystray, tkinter and the engine.

tkinter owns the main thread; pystray runs its own message loop in a second
thread. Menu clicks are handed to the tk thread through a queue.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import pystray
from PIL import Image, ImageDraw, ImageTk

from . import autostart
from .config import Settings, app_dir
from .engine import Engine, Status
from .settings_window import SettingsWindow

log = logging.getLogger(__name__)
APP_TITLE = "Capture Compressor"
COLORS = {
    "idle": (34, 160, 90),
    "compressing": (230, 140, 20),
    "paused": (130, 130, 130),
    "error": (210, 50, 50),
}


def make_icon(state: str) -> Image.Image:
    """A colored disc with a white 'shrink' arrow; color shows the state."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill=COLORS.get(state, COLORS["idle"]) + (255,))
    white = (255, 255, 255, 255)
    d.rectangle((26, 12, 38, 30), fill=white)              # arrow shaft
    d.polygon([(16, 30), (48, 30), (32, 46)], fill=white)  # arrow head
    d.rectangle((16, 49, 48, 54), fill=white)              # "floor"
    return img


def _already_running() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "Local\\CaptureCompressorSingleInstance")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


class TrayApp:
    def __init__(self, settings: Settings, first_run: bool) -> None:
        self.settings = settings
        self.first_run = first_run
        self.calls: queue.Queue = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self._window_icon = ImageTk.PhotoImage(make_icon("idle"))
        self.root.iconphoto(True, self._window_icon)  # also used by the Settings window
        self.settings_window: SettingsWindow | None = None
        self.engine = Engine(settings, on_status=self._on_status, on_notify=self._notify)
        self.icon = pystray.Icon(
            "CaptureCompressor",
            make_icon("idle"),
            f"{APP_TITLE} - starting",
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: self.engine.status.text()[:60], None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Settings...", self._ui(self.open_settings), default=True),
                pystray.MenuItem(
                    lambda item: "Resume" if self.engine.paused else "Pause",
                    lambda: self.engine.set_paused(not self.engine.paused),
                ),
                pystray.MenuItem("Open folder", lambda: _open(self.settings.watch_folder)),
                pystray.MenuItem("Open log", lambda: _open(str(app_dir() / "capture_compressor.log"))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._ui(self.exit)),
            ),
        )

    def run(self) -> None:
        if self.first_run:
            self.settings.save()
        try:
            autostart.sync(self.settings.start_with_windows)
        except OSError:
            log.exception("Could not update the autostart entry")
        threading.Thread(target=self.icon.run, name="tray", daemon=True).start()
        # Encoder test takes a moment; don't block the tray from appearing.
        threading.Thread(target=self.engine.start, name="engine-start", daemon=True).start()
        self.root.after(100, self._pump)
        self.root.mainloop()

    # ---- thread hand-off ---------------------------------------------------

    def _ui(self, fn):
        """Wrap a menu callback so it runs on the tk thread."""
        return lambda *args: self.calls.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self.calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("UI action failed")
        self.root.after(100, self._pump)

    # ---- engine callbacks (worker thread) ----------------------------------

    def _on_status(self, status: Status) -> None:
        self.icon.icon = make_icon(status.state)
        self.icon.title = f"{APP_TITLE} - {status.text()}"[:127]
        self.icon.update_menu()

    def _notify(self, message: str) -> None:
        log.info("Notification: %s", message)
        try:
            self.icon.notify(message[:250], APP_TITLE)
        except Exception:
            log.exception("Could not show a notification")

    # ---- actions (tk thread) -----------------------------------------------

    def open_settings(self) -> None:
        if self.settings_window and self.settings_window.is_open():
            self.settings_window.focus()
            return
        self.settings_window = SettingsWindow(
            self.root, self.settings, self.engine.encoder, self._save_settings
        )

    def _save_settings(self, new: Settings) -> None:
        new.save()
        self.settings = new
        log.info("Settings saved: %s", new)
        try:
            autostart.sync(new.start_with_windows)
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Could not change autostart: {e}")
        threading.Thread(target=self.engine.apply_settings, args=(new,), daemon=True).start()

    def exit(self) -> None:
        log.info("Exiting")
        self.icon.stop()
        self.engine.stop()
        self.root.quit()


def _open(path: str) -> None:
    try:
        os.startfile(path)
    except OSError:
        log.exception("Could not open %s", path)


def run_tray(settings: Settings, first_run: bool) -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp tkinter on HiDPI screens
    except (AttributeError, OSError):
        pass
    if _already_running():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_TITLE, "Capture Compressor is already running (see the tray).")
        return
    TrayApp(settings, first_run).run()
