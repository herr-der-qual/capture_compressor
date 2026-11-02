"""The Settings window (tkinter)."""

from __future__ import annotations

import tkinter
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import decisions
from .settings import Settings

WINDOW_TITLE = "Capture Compressor - Settings"
HINT_COLOR = "gray"
WARNING_COLOR = "#b45309"
TOPMOST_FLASH_MILLISECONDS = 200


class SettingsWindow:
    def __init__(
        self,
        root: tkinter.Tk,
        settings: Settings,
        active_encoder: str,
        on_save: Callable[[Settings], None],
    ) -> None:
        self.settings = settings
        self.active_encoder = active_encoder
        self.on_save = on_save
        self.window = tkinter.Toplevel(root)
        self.window.title(WINDOW_TITLE)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self._create_variables()
        self._build_form()
        self._center_on_screen()
        self.bring_to_front()

    # ---- layout -----------------------------------------------------------

    def _create_variables(self) -> None:
        self.watch_folder = tkinter.StringVar(value=self.settings.watch_folder)
        self.encoder_description = tkinter.StringVar(
            value=decisions.ENCODER_DESCRIPTIONS[self.settings.encoder]
        )
        self.quality = tkinter.IntVar(value=self.settings.quality)
        self.ffmpeg_path = tkinter.StringVar(value=self.settings.ffmpeg_path)
        self.permanent_delete = tkinter.BooleanVar(value=self.settings.permanent_delete)
        self.start_with_windows = tkinter.BooleanVar(value=self.settings.start_with_windows)

    def _build_form(self) -> None:
        self.form = ttk.Frame(self.window, padding=12)
        self.form.grid(sticky="nsew")
        self.form.columnconfigure(1, weight=1)
        self.next_row = 0
        self._add_path_row("Watch folder:", self.watch_folder, self._browse_watch_folder)
        self._add_encoder_row()
        self._add_quality_row()
        self._add_path_row("ffmpeg location:", self.ffmpeg_path, self._browse_ffmpeg)
        self._add_hint("Leave empty to use ffmpeg from PATH.")
        self._add_checkbox("Delete originals permanently (instead of Recycle Bin)",
                           self.permanent_delete, top_padding=10)
        self._add_checkbox("Start with Windows", self.start_with_windows)
        self._add_buttons()

    def _take_row(self) -> int:
        row = self.next_row
        self.next_row += 1
        return row

    def _add_label(self, text: str, row: int) -> None:
        ttk.Label(self.form, text=text).grid(row=row, column=0, sticky="w", pady=4)

    def _add_path_row(self, label: str, variable: tkinter.StringVar, browse: Callable) -> None:
        row = self._take_row()
        self._add_label(label, row)
        ttk.Entry(self.form, textvariable=variable, width=50).grid(row=row, column=1, sticky="ew")
        ttk.Button(self.form, text="Browse...", command=browse).grid(row=row, column=2, padx=(6, 0))

    def _add_encoder_row(self) -> None:
        row = self._take_row()
        self._add_label("Encoder:", row)
        ttk.Combobox(
            self.form, textvariable=self.encoder_description, state="readonly", width=36,
            values=list(decisions.ENCODER_DESCRIPTIONS.values()),
        ).grid(row=row, column=1, sticky="w")
        if self.active_encoder and self.active_encoder != self.settings.encoder:
            self._add_hint(
                f"{self.settings.encoder} does not work on this PC, "
                f"currently using {self.active_encoder}. See the log.",
                color=WARNING_COLOR,
            )

    def _add_quality_row(self) -> None:
        row = self._take_row()
        self._add_label("Quality:", row)
        quality_frame = ttk.Frame(self.form)
        quality_frame.grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Spinbox(
            quality_frame, textvariable=self.quality, width=5,
            from_=decisions.LOWEST_QUALITY_VALUE, to=decisions.HIGHEST_QUALITY_VALUE,
        ).pack(side="left")
        ttk.Label(
            quality_frame, foreground=HINT_COLOR,
            text=f"  lower = better quality, bigger files (default {decisions.DEFAULT_QUALITY})",
        ).pack(side="left")

    def _add_hint(self, text: str, color: str = HINT_COLOR) -> None:
        ttk.Label(self.form, text=text, foreground=color).grid(
            row=self._take_row(), column=1, columnspan=2, sticky="w")

    def _add_checkbox(self, text: str, variable: tkinter.BooleanVar, top_padding: int = 2) -> None:
        ttk.Checkbutton(self.form, text=text, variable=variable).grid(
            row=self._take_row(), column=0, columnspan=3, sticky="w", pady=(top_padding, 2))

    def _add_buttons(self) -> None:
        buttons = ttk.Frame(self.form)
        buttons.grid(row=self._take_row(), column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Save", command=self._save, default="active").pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.close).pack(side="left", padx=(6, 0))
        self.window.bind("<Return>", lambda event: self._save())
        self.window.bind("<Escape>", lambda event: self.close())

    def _center_on_screen(self) -> None:
        self.window.update_idletasks()
        left = (self.window.winfo_screenwidth() - self.window.winfo_width()) // 2
        top = (self.window.winfo_screenheight() - self.window.winfo_height()) // 3
        self.window.geometry(f"+{left}+{top}")

    # ---- window state -----------------------------------------------------

    def bring_to_front(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.window.after(TOPMOST_FLASH_MILLISECONDS,
                          lambda: self.window.attributes("-topmost", False))
        self.window.focus_force()

    def is_open(self) -> bool:
        return bool(self.window.winfo_exists())

    def close(self) -> None:
        self.window.destroy()

    # ---- actions ----------------------------------------------------------

    def _browse_watch_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self.window, initialdir=self.watch_folder.get() or None)
        if folder:
            self.watch_folder.set(str(Path(folder)))

    def _browse_ffmpeg(self) -> None:
        ffmpeg = filedialog.askopenfilename(
            parent=self.window, title="Select ffmpeg.exe",
            filetypes=[("ffmpeg", "ffmpeg.exe"), ("Programs", "*.exe")],
        )
        if ffmpeg:
            self.ffmpeg_path.set(str(Path(ffmpeg)))

    def _save(self) -> None:
        problem = self._find_input_problem()
        if problem:
            messagebox.showerror("Settings", problem, parent=self.window)
            return
        self.on_save(self._collect_settings())
        self.close()

    def _find_input_problem(self) -> str | None:
        folder = self.watch_folder.get().strip()
        if not Path(folder).is_dir():
            return f"Folder does not exist:\n{folder}"
        try:
            quality = int(self.quality.get())
        except (tkinter.TclError, ValueError):
            return "Quality must be a number."
        if decisions.clamp_quality(quality) != quality:
            return (f"Quality must be between {decisions.LOWEST_QUALITY_VALUE} "
                    f"and {decisions.HIGHEST_QUALITY_VALUE}.")
        return None

    def _collect_settings(self) -> Settings:
        chosen_description = self.encoder_description.get()
        encoder = next(name for name, description in decisions.ENCODER_DESCRIPTIONS.items()
                       if description == chosen_description)
        return replace(
            self.settings,
            watch_folder=str(Path(self.watch_folder.get().strip())),
            encoder=encoder,
            quality=int(self.quality.get()),
            ffmpeg_path=self.ffmpeg_path.get().strip(),
            permanent_delete=self.permanent_delete.get(),
            start_with_windows=self.start_with_windows.get(),
        )
