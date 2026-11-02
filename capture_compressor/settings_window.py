"""The Settings window (tkinter)."""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import logic
from .config import Settings


class SettingsWindow:
    def __init__(
        self,
        root: tk.Tk,
        settings: Settings,
        active_encoder: str,
        on_save: Callable[[Settings], None],
    ) -> None:
        self.settings = settings
        self.on_save = on_save
        self.win = win = tk.Toplevel(root)
        win.title("Capture Compressor - Settings")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)

        self.folder = tk.StringVar(value=settings.watch_folder)
        self.encoder = tk.StringVar(value=logic.ENCODERS[settings.encoder])
        self.quality = tk.IntVar(value=settings.quality)
        self.ffmpeg = tk.StringVar(value=settings.ffmpeg_path)
        self.permanent = tk.BooleanVar(value=settings.permanent_delete)
        self.autostart = tk.BooleanVar(value=settings.start_with_windows)

        f = ttk.Frame(win, padding=12)
        f.grid(sticky="nsew")
        f.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(f, text="Watch folder:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.folder, width=50).grid(row=row, column=1, sticky="ew")
        ttk.Button(f, text="Browse...", command=self._browse_folder).grid(row=row, column=2, padx=(6, 0))
        row += 1

        ttk.Label(f, text="Encoder:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            f, textvariable=self.encoder, values=list(logic.ENCODERS.values()),
            state="readonly", width=36,
        ).grid(row=row, column=1, sticky="w")
        row += 1
        if active_encoder and active_encoder != settings.encoder:
            ttk.Label(
                f, foreground="#b45309",
                text=f"{settings.encoder} does not work on this PC, currently using {active_encoder}. See the log.",
            ).grid(row=row, column=1, columnspan=2, sticky="w")
            row += 1

        ttk.Label(f, text="Quality:").grid(row=row, column=0, sticky="w", pady=4)
        q = ttk.Frame(f)
        q.grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Spinbox(q, from_=logic.QUALITY_RANGE[0], to=logic.QUALITY_RANGE[1],
                    textvariable=self.quality, width=5).pack(side="left")
        ttk.Label(q, text=f"  lower = better quality, bigger files (default {logic.DEFAULT_QUALITY})",
                  foreground="gray").pack(side="left")
        row += 1

        ttk.Label(f, text="ffmpeg location:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.ffmpeg, width=50).grid(row=row, column=1, sticky="ew")
        ttk.Button(f, text="Browse...", command=self._browse_ffmpeg).grid(row=row, column=2, padx=(6, 0))
        row += 1
        ttk.Label(f, text="Leave empty to use ffmpeg from PATH.", foreground="gray").grid(
            row=row, column=1, sticky="w")
        row += 1

        ttk.Checkbutton(f, text="Delete originals permanently (instead of Recycle Bin)",
                        variable=self.permanent).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 2))
        row += 1
        ttk.Checkbutton(f, text="Start with Windows", variable=self.autostart).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=2)
        row += 1

        buttons = ttk.Frame(f)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Save", command=self._save, default="active").pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.close).pack(side="left", padx=(6, 0))
        win.bind("<Return>", lambda e: self._save())
        win.bind("<Escape>", lambda e: self.close())

        win.update_idletasks()
        x = (win.winfo_screenwidth() - win.winfo_width()) // 2
        y = (win.winfo_screenheight() - win.winfo_height()) // 3
        win.geometry(f"+{x}+{y}")
        self.focus()

    def focus(self) -> None:
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.win.after(200, lambda: self.win.attributes("-topmost", False))
        self.win.focus_force()

    def is_open(self) -> bool:
        return bool(self.win.winfo_exists())

    def close(self) -> None:
        self.win.destroy()

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(parent=self.win, initialdir=self.folder.get() or None)
        if path:
            self.folder.set(str(Path(path)))

    def _browse_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.win, title="Select ffmpeg.exe",
            filetypes=[("ffmpeg", "ffmpeg.exe"), ("Programs", "*.exe")],
        )
        if path:
            self.ffmpeg.set(str(Path(path)))

    def _save(self) -> None:
        folder = self.folder.get().strip()
        if not Path(folder).is_dir():
            messagebox.showerror("Settings", f"Folder does not exist:\n{folder}", parent=self.win)
            return
        try:
            quality = int(self.quality.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Settings", "Quality must be a number.", parent=self.win)
            return
        low, high = logic.QUALITY_RANGE
        if not low <= quality <= high:
            messagebox.showerror("Settings", f"Quality must be between {low} and {high}.", parent=self.win)
            return
        label = self.encoder.get()
        encoder = next(k for k, v in logic.ENCODERS.items() if v == label)
        new = replace(
            self.settings,
            watch_folder=str(Path(folder)),
            encoder=encoder,
            quality=quality,
            ffmpeg_path=self.ffmpeg.get().strip(),
            permanent_delete=self.permanent.get(),
            start_with_windows=self.autostart.get(),
        )
        self.on_save(new)
        self.close()
