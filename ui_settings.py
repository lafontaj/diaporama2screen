#!/usr/bin/env python3
"""
ui_settings.py — The production panel: format, timings and music.

Kept apart from the main window so that neither file becomes the kind of
monolith that is slow to read and slow to load.
"""
__version__ = "1.4.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import tkinter as tk
from tkinter import ttk

import paths
import project as project_mod
import ui_dialogs

try:
    from i18n import _, ngettext
except ImportError:
    def _(s):
        return s

    def ngettext(singular, plural, n):
        return singular if n == 1 else plural

MUSIC_EXTENSIONS = (".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav")


def format_duration(seconds):
    """Seconds as m:ss, or h:mm:ss beyond an hour."""
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{}:{:02d}".format(minutes, secs)


class SettingsPanel(ttk.Frame):
    """Everything that describes the video to be produced."""

    def __init__(self, master, app):
        super().__init__(master, padding=(8, 6))
        self.app = app
        self._loading = False
        self._build()

    # ---------- construction ----------

    def _build(self):
        self.columnconfigure(3, weight=1)

        ttk.Label(self, text=_("Format:")).grid(row=0, column=0, sticky="w")
        self.var_format = tk.StringVar(value="HD")
        box = ttk.Combobox(self, textvariable=self.var_format, width=16,
                           state="readonly",
                           values=["HD", "4K"])
        box.grid(row=0, column=1, sticky="w", padx=(4, 16))
        box.bind("<<ComboboxSelected>>", self._on_change)
        self.lbl_size = ttk.Label(self, text="1920 x 1080")
        self.lbl_size.grid(row=0, column=2, sticky="w", padx=(0, 16))

        timings = ttk.Frame(self)
        timings.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.var_seconds = tk.StringVar(value="10")
        self.var_crossfade = tk.StringVar(value="2")
        self.var_black = tk.StringVar(value="2")

        self._spin(timings, _("Seconds per photo:"), self.var_seconds,
                   0.5, 60.0, 0)
        self._spin(timings, _("Cross-fade:"), self.var_crossfade,
                   0.0, 10.0, 2)
        self._spin(timings, _("Fade from and to black:"), self.var_black,
                   0.0, 10.0, 4)

        music = ttk.LabelFrame(self, text=_("Music"), padding=(6, 4))
        music.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=(10, 0))
        music.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.music_list = tk.Listbox(music, height=4, selectmode=tk.EXTENDED,
                                     activestyle="none", exportselection=False)
        self.music_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(music, orient="vertical",
                               command=self.music_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.music_list.configure(yscrollcommand=scroll.set)
        music.rowconfigure(0, weight=1)

        buttons = ttk.Frame(music)
        buttons.grid(row=0, column=2, sticky="n", padx=(6, 0))
        ttk.Button(buttons, text=_("Add files…"),
                   command=self.add_music_files).pack(fill="x")
        ttk.Button(buttons, text=_("Add a folder…"),
                   command=self.add_music_folder).pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text=_("Remove"),
                   command=self.remove_music).pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text=_("Up"),
                   command=lambda: self.move_music(-1)).pack(fill="x",
                                                             pady=(10, 0))
        ttk.Button(buttons, text=_("Down"),
                   command=lambda: self.move_music(1)).pack(fill="x",
                                                            pady=(4, 0))

        self.lbl_music = ttk.Label(music, text="")
        self.lbl_music.grid(row=1, column=0, columnspan=3, sticky="w",
                            pady=(4, 0))

        self.var_normalise = tk.BooleanVar(value=True)
        ttk.Checkbutton(music, variable=self.var_normalise,
                        command=self._on_change,
                        text=_("Even out the level between pieces")).grid(
                            row=2, column=0, columnspan=3, sticky="w",
                            pady=(2, 0))
        self.var_trim = tk.BooleanVar(value=True)
        ttk.Checkbutton(music, variable=self.var_trim,
                        command=self._on_change,
                        text=_("Trim the silence at each end of a piece")
                        ).grid(row=3, column=0, columnspan=3, sticky="w")

        output = ttk.LabelFrame(self, text=_("Where the results are written"),
                                padding=(6, 4))
        output.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        output.columnconfigure(1, weight=1)

        ttk.Label(output, text=_("Images:")).grid(row=0, column=0, sticky="w")
        self.lbl_images = ttk.Label(output, text="", anchor="w")
        self.lbl_images.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(output, text=_("Change…"),
                   command=self.change_images_dir).grid(row=0, column=2)
        ttk.Button(output, text=_("Automatic"),
                   command=lambda: self._reset_output("images_dir")).grid(
            row=0, column=3, padx=(4, 0))

        ttk.Label(output, text=_("Video:")).grid(row=1, column=0, sticky="w",
                                                 pady=(4, 0))
        self.lbl_video = ttk.Label(output, text="", anchor="w")
        self.lbl_video.grid(row=1, column=1, sticky="ew", padx=(6, 6),
                            pady=(4, 0))
        ttk.Button(output, text=_("Change…"),
                   command=self.change_video_path).grid(row=1, column=2,
                                                        pady=(4, 0))
        ttk.Button(output, text=_("Automatic"),
                   command=lambda: self._reset_output("video_path")).grid(
            row=1, column=3, padx=(4, 0), pady=(4, 0))

        bottom = ttk.Frame(self)
        bottom.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        bottom.columnconfigure(0, weight=1)
        self.lbl_estimate = ttk.Label(bottom, text="")
        self.lbl_estimate.grid(row=0, column=0, sticky="w")
        self.btn_produce = ttk.Button(bottom, text=_("Produce the video"),
                                      state="disabled",
                                      command=self.app.on_produce)
        self.btn_produce.grid(row=0, column=1, sticky="e")

    def _spin(self, parent, label, var, lo, hi, column):
        ttk.Label(parent, text=label).grid(row=0, column=column, sticky="w")
        spin = ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                           increment=0.5, width=6, command=self._on_change)
        spin.grid(row=0, column=column + 1, sticky="w", padx=(4, 16))
        spin.bind("<FocusOut>", self._on_change)
        spin.bind("<Return>", self._on_change)

    # ---------- music ----------

    def add_music_files(self):
        names = ui_dialogs.pick_audio(self.winfo_toplevel(),
                                      title=_("Add music files"),
                                      initialdir=self._music_start())
        if names:
            self._append_music(names)

    def add_music_folder(self):
        folder = ui_dialogs.pick_directory(self.winfo_toplevel(),
                                           title=_("Add a music folder"),
                                           initialdir=self._music_start())
        if not folder:
            return
        found = []
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if (os.path.isfile(full)
                    and os.path.splitext(name)[1].lower() in MUSIC_EXTENSIONS):
                found.append(full)
        self._append_music(found)

    def _music_start(self):
        files = self.app.proj.settings.get("music_files", [])
        if files:
            return os.path.dirname(files[-1])
        return paths.output_dir()

    def _append_music(self, names):
        files = list(self.app.proj.settings.get("music_files", []))
        for n in names:
            full = os.path.abspath(n)
            if full not in files:
                files.append(full)
        self.app.proj.set_setting("music_files", files)
        self.refresh_music()
        self.app.update_title()

    def remove_music(self):
        picked = list(self.music_list.curselection())
        if not picked:
            return
        files = list(self.app.proj.settings.get("music_files", []))
        for i in sorted(picked, reverse=True):
            if 0 <= i < len(files):
                del files[i]
        self.app.proj.set_setting("music_files", files)
        self.refresh_music()
        self.app.update_title()

    def move_music(self, delta):
        picked = list(self.music_list.curselection())
        if not picked:
            return
        files = list(self.app.proj.settings.get("music_files", []))
        order = sorted(picked, reverse=(delta > 0))
        new = []
        for i in order:
            j = i + delta
            if 0 <= j < len(files):
                files[i], files[j] = files[j], files[i]
                new.append(j)
            else:
                new.append(i)
        self.app.proj.set_setting("music_files", files)
        self.refresh_music()
        self.music_list.selection_clear(0, tk.END)
        for i in new:
            self.music_list.selection_set(i)
        self.app.update_title()

    def refresh_music(self):
        files = self.app.proj.settings.get("music_files", [])
        self.music_list.delete(0, tk.END)
        for f in files:
            missing = "" if os.path.isfile(f) else "  " + _("(missing)")
            self.music_list.insert(tk.END, os.path.basename(f) + missing)
        if not files:
            self.lbl_music.configure(text=_("No music: the video will be silent."))
        else:
            self.lbl_music.configure(
                text=ngettext(
                    "{n} piece, played then looped.",
                    "{n} pieces, played in this order then looped.",
                    len(files)).format(
                    n=len(files)))

    # ---------- where the results go ----------

    def change_images_dir(self):
        folder = ui_dialogs.pick_directory(
            self.winfo_toplevel(),
            title=_("Folder for the laid-out images"),
            initialdir=self.app.proj.images_dir())
        if folder:
            self.app.proj.set_setting("images_dir", folder)
            self.refresh_outputs()
            self.app.update_title()

    def change_video_path(self):
        current = self.app.proj.video_path()
        name = ui_dialogs.pick_save(
            self.winfo_toplevel(), title=_("Where to write the video"),
            initialdir=os.path.dirname(current),
            initialfile=os.path.basename(current),
            suffix=".mp4", pattern="*.mp4", pattern_label=_("Video"))
        if name:
            self.app.proj.set_setting("video_path", name)
            self.refresh_outputs()
            self.app.update_title()

    def _reset_output(self, key):
        self.app.proj.set_setting(key, "")
        self.refresh_outputs()
        self.app.update_title()

    def refresh_outputs(self):
        proj = self.app.proj
        auto = _("  (automatic)")
        self.lbl_images.configure(
            text=proj.images_dir()
            + (auto if proj.images_dir_is_automatic() else ""))
        self.lbl_video.configure(
            text=proj.video_path()
            + (auto if proj.video_path_is_automatic() else ""))

    # ---------- settings <-> widgets ----------

    def load_from_project(self):
        """Fill the widgets from the project. Does not mark it modified."""
        self._loading = True
        s = self.app.proj.settings
        self.var_format.set(s.get("format", "HD"))
        self.var_seconds.set(self._clean(s.get("seconds_per_photo", 10)))
        self.var_crossfade.set(self._clean(s.get("crossfade", 2)))
        self.var_black.set(self._clean(s.get("black_fade", 2)))
        self.var_normalise.set(bool(s.get("normalise_music", True)))
        self.var_trim.set(bool(s.get("trim_music_silence", True)))
        self._loading = False
        self.refresh_music()
        self.refresh_outputs()
        self.refresh_estimate()

    @staticmethod
    def _clean(value):
        try:
            f = float(value)
        except (TypeError, ValueError):
            return "0"
        return str(int(f)) if f == int(f) else str(f)

    def _number(self, var, fallback):
        try:
            return float(str(var.get()).replace(",", "."))
        except (TypeError, ValueError):
            return float(fallback)

    def _on_change(self, event=None):
        if self._loading:
            return
        proj = self.app.proj
        proj.set_setting("format", self.var_format.get())
        proj.set_setting("seconds_per_photo",
                         self._number(self.var_seconds, 10))
        proj.set_setting("crossfade", self._number(self.var_crossfade, 2))
        proj.set_setting("black_fade", self._number(self.var_black, 2))
        proj.set_setting("normalise_music", bool(self.var_normalise.get()))
        proj.set_setting("trim_music_silence", bool(self.var_trim.get()))
        self.refresh_estimate()
        self.app.update_title()

    def refresh_estimate(self):
        width, height = self.app.proj.size
        self.lbl_size.configure(text="{} x {}".format(width, height))
        self.refresh_outputs()
        count = len(self.app.proj.photos)
        if count == 0:
            self.lbl_estimate.configure(text=_("No photo in the slideshow yet."))
            self.btn_produce.configure(state="disabled")
            return
        self.btn_produce.configure(state="normal")
        self.lbl_estimate.configure(
            text=ngettext("{n} photo — {duration} of video",
                          "{n} photos — {duration} of video", count).format(
                n=count, duration=format_duration(self.app.proj.duration())))
