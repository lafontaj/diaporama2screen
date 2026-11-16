#!/usr/bin/env python3
"""
ui_import.py — Importing a selection made in digiKam, by tag.

The window sweeps a folder once, shows every tag found with the number of
photographs carrying it, and adds the photographs of the ticked tags to the
slideshow. Importing only ever ADDS: photographs already in the slideshow
are left where they are, and replacing it outright is a separate box that
asks again before doing anything.

Tags are listed rather than typed. A library holds hundreds of them, so the
list has a filter that narrows it as it is typed, and ticks are kept in a
set of their own so that narrowing the list never loses a choice made
before — the same arrangement as the thumbnail board, for the same reason.
"""
__version__ = "1.1.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import queue
import threading
import tkinter as tk
import unicodedata
from tkinter import ttk

import tags as tags_mod
import ui_dialogs

try:
    from i18n import _, ngettext
except ImportError:
    def _(s):
        return s

    def ngettext(singular, plural, n):
        return singular if n == 1 else plural

TICK = "✓"


def _fold(text):
    """Lower case and without accents, for a filter that forgives both.
    Typing "evenements" should find "Événements"."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class TagImport(tk.Toplevel):
    """Choose tags in a folder and return the photographs they carry."""

    def __init__(self, parent, folder, title=None):
        super().__init__(parent)
        self.withdraw()
        self.result = None            # list of paths, or None when cancelled
        self.replace = False

        self.title(title or _("Import from a tag"))
        self.geometry("820x560")
        self.minsize(640, 440)
        self.transient(parent)

        self._folder = folder or os.path.expanduser("~")
        self._tags = {}               # label -> [paths]
        self._shown = []              # labels currently in the list
        self._chosen = set()          # labels ticked, filter or no filter
        self._scan = None
        self._queue = queue.Queue()
        self._poll = None

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())

        self.update_idletasks()
        self._centre(parent)
        self.deiconify()
        self.grab_set()
        self.wait_window(self)

    # ---------- construction ----------

    def _build(self):
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text=_("Folder:")).grid(row=0, column=0, sticky="w")
        self.lbl_folder = ttk.Label(top, text=self._folder, anchor="w")
        self.lbl_folder.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        self.btn_folder = ttk.Button(top, text=_("Change…"),
                                     command=self._choose_folder)
        self.btn_folder.grid(row=0, column=2)

        line = ttk.Frame(self, padding=(10, 0))
        line.pack(fill="x")
        self.var_recursive = tk.BooleanVar(value=True)
        self.chk_recursive = ttk.Checkbutton(
            line, text=_("Include subfolders"), variable=self.var_recursive)
        self.chk_recursive.pack(side="left")
        self.btn_scan = ttk.Button(line, text=_("Look for tags"),
                                   command=self._start_scan)
        self.btn_scan.pack(side="left", padx=(18, 0))
        self.progress = ttk.Progressbar(line, mode="indeterminate",
                                        length=160)
        self.lbl_progress = ttk.Label(line, text="")

        filtre = ttk.Frame(self, padding=(10, 8))
        filtre.pack(fill="x")
        ttk.Label(filtre, text=_("Filter:")).pack(side="left")
        self.var_filter = tk.StringVar()
        self.entry_filter = ttk.Entry(filtre, textvariable=self.var_filter,
                                      width=28)
        self.entry_filter.pack(side="left", padx=(6, 0))
        self.var_filter.trace_add("write", lambda *a: self._refill())
        ttk.Button(filtre, text=_("Clear"),
                   command=lambda: self.var_filter.set("")).pack(
                       side="left", padx=(6, 0))
        self.lbl_shown = ttk.Label(filtre, text="")
        self.lbl_shown.pack(side="right")

        middle = ttk.Frame(self, padding=(10, 0))
        middle.pack(fill="both", expand=True)
        columns = ("tick", "label", "count")
        self.tree = ttk.Treeview(middle, columns=columns, show="headings",
                                 selectmode="browse")
        self.tree.heading("tick", text="")
        self.tree.heading("label", text=_("Tag"))
        self.tree.heading("count", text=_("Photos"))
        self.tree.column("tick", width=34, anchor="center", stretch=False)
        self.tree.column("label", width=560, anchor="w")
        self.tree.column("count", width=80, anchor="e", stretch=False)
        scroll = ttk.Scrollbar(middle, orient="vertical",
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", lambda e: self._toggle_selected())
        self.tree.bind("<Return>", lambda e: self._toggle_selected())

        bottom = ttk.Frame(self, padding=(10, 8))
        bottom.pack(fill="x")
        self.lbl_state = ttk.Label(bottom, text="")
        self.lbl_state.pack(side="left")

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        self.var_replace = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons, text=_("Replace the slideshow instead of "
                                        "adding to it"),
                        variable=self.var_replace).pack(side="left")
        ttk.Button(buttons, text=_("Cancel"),
                   command=self._cancel).pack(side="right")
        self.btn_add = ttk.Button(buttons, text=_("Add"), command=self._add)
        self.btn_add.pack(side="right", padx=(0, 8))
        self.btn_add.state(["disabled"])

        self._refresh_state()

    def _centre(self, parent):
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px = py = pw = ph = 0
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("+{}+{}".format(px + max(0, (pw - w) // 2),
                                      py + max(0, (ph - h) // 3)))

    # ---------- the sweep ----------

    def _choose_folder(self):
        folder = ui_dialogs.pick_directory(
            self, title=_("Folder to sweep for tags"),
            initialdir=self._folder)
        if folder:
            self._folder = folder
            self.lbl_folder.configure(text=folder)

    def _start_scan(self):
        if self._scan is not None:        # already running: this stops it
            self._scan.cancel()
            return
        self._tags = {}
        self._chosen.clear()
        self._refill()
        self._scan = tags_mod.TagScan(self._folder,
                                      recursive=self.var_recursive.get())
        self._set_scanning(True)
        threading.Thread(target=self._work, daemon=True).start()
        self._poll = self.after(100, self._drain)

    def _work(self):
        result = self._scan.run(progress=self._on_progress)
        self._queue.put(("result",) + tuple(result))

    def _on_progress(self, stage, done, total):
        """Appelé depuis le fil du balayage : on ne touche pas à Tk ici, on
        dépose le chiffre dans la file que la fenêtre vide elle-même."""
        self._queue.put(("progress", stage, done, total))

    def _drain(self):
        message = None
        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break
            if message[0] == "progress":
                self._show_progress(message[1], message[2], message[3])
                message = None
                continue
            break                      # a result ends the sweep
        if message is None:
            self._poll = self.after(100, self._drain)
            return
        _kind, found, files, error = message
        self._poll = None
        self._scan = None
        self._set_scanning(False)
        if error == "cancelled":
            self._refresh_state()
            return
        if error:
            ui_dialogs.error(self, {
                "folder": _("That folder cannot be read."),
                "exiftool": _("exiftool is not installed, so tags cannot be "
                              "read.\n\n  sudo apt install "
                              "libimage-exiftool-perl"),
                "timeout": _("The sweep took too long and was stopped."),
                "output": _("exiftool answered something unexpected."),
            }.get(error, error))
            return
        self._tags = found
        self._files = files
        self._refill()
        if not found:
            ui_dialogs.info(self, _("No tag was found in that folder. In "
                                    "digiKam, check that tags are written "
                                    "into the files themselves."))

    def _show_progress(self, stage, done, total):
        if stage == "walk":
            self.lbl_progress.configure(text=_("Looking through the "
                                               "folders…"))
            return
        if total <= 0:
            self.lbl_progress.configure(text="")
            return
        if str(self.progress.cget("mode")) != "determinate":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=total)
        self.progress.configure(value=done)
        self.lbl_progress.configure(
            text=_("{done} of {total} files read").format(done=done,
                                                          total=total))

    def _set_scanning(self, busy):
        state = "disabled" if busy else "normal"
        self.btn_folder.configure(state=state)
        self.chk_recursive.configure(state=state)
        self.entry_filter.configure(state=state)
        self.btn_scan.configure(text=_("Stop") if busy
                                else _("Look for tags"))
        if busy:
            self.progress.configure(mode="indeterminate", value=0)
            self.progress.pack(side="left", padx=(12, 0))
            self.lbl_progress.pack(side="left", padx=(8, 0))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.lbl_progress.pack_forget()
            self.lbl_progress.configure(text="")

    # ---------- the list ----------

    def _refill(self):
        needle = _fold(self.var_filter.get().strip())
        self.tree.delete(*self.tree.get_children())
        self._shown = []
        for label in sorted(self._tags, key=_fold):
            if needle and needle not in _fold(label):
                continue
            self._shown.append(label)
            self.tree.insert(
                "", "end", iid=str(len(self._shown) - 1),
                values=(TICK if label in self._chosen else "",
                        label, len(self._tags[label])))
        total = len(self._tags)
        if total:
            self.lbl_shown.configure(text=_("{shown} of {total} tags").format(
                shown=len(self._shown), total=total))
        else:
            self.lbl_shown.configure(text="")
        self._refresh_state()

    def _on_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row:
            self._toggle(int(row))

    def _toggle_selected(self):
        for row in self.tree.selection():
            self._toggle(int(row))

    def _toggle(self, position):
        if position >= len(self._shown):
            return
        label = self._shown[position]
        if label in self._chosen:
            self._chosen.discard(label)
        else:
            self._chosen.add(label)
        self.tree.set(str(position), "tick",
                      TICK if label in self._chosen else "")
        self._refresh_state()

    def _photos(self):
        """The photographs of every ticked tag, each one once."""
        paths = set()
        for label in self._chosen:
            paths.update(self._tags.get(label, ()))
        return sorted(paths)

    def _refresh_state(self):
        photos = self._photos()
        if self._chosen:
            self.lbl_state.configure(text="{}   ·   {}".format(
                ngettext("{n} tag ticked", "{n} tags ticked",
                         len(self._chosen)).format(n=len(self._chosen)),
                ngettext("{n} photo", "{n} photos",
                         len(photos)).format(n=len(photos))))
            self.btn_add.state(["!disabled"])
        else:
            self.lbl_state.configure(
                text=_("Tick a tag to choose its photographs."))
            self.btn_add.state(["disabled"])

    # ---------- leaving ----------

    def _add(self):
        photos = self._photos()
        if not photos:
            return
        if self.var_replace.get():
            if not ui_dialogs.confirm(
                    self,
                    ngettext(
                        "The slideshow will be emptied and replaced by "
                        "{n} photograph. The photographs now in it will be "
                        "dropped, and nothing on disk is touched. Continue?",
                        "The slideshow will be emptied and replaced by "
                        "{n} photographs. The photographs now in it will be "
                        "dropped, and nothing on disk is touched. Continue?",
                        len(photos)).format(n=len(photos)),
                    ok_text=_("Replace"), kind="warning"):
                return
        self.result = photos
        self.replace = bool(self.var_replace.get())
        self._close()

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        if self._scan is not None:
            self._scan.cancel()
        if self._poll is not None:
            try:
                self.after_cancel(self._poll)
            except Exception:
                pass
        self.destroy()


def choose(parent, folder, title=None):
    """Open the window. Returns (paths, replace); paths is None on cancel."""
    dialog = TagImport(parent, folder, title=title)
    return dialog.result, dialog.replace
