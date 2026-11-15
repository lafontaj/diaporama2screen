#!/usr/bin/env python3
"""
ui_picker.py — Choosing photos by looking at them.

A file selector shows names. Scanned photographs rarely have meaningful names,
so choosing from a list of "Helene_0032.jpg" is guesswork. zenity has no
preview at all; yad can show one image at a time, which still means clicking
every line. This dialog shows a whole folder as thumbnails with a tick box, so
the decision is made on the picture.

It navigates on its own: the folder bar at the top changes folder, and ticks
are remembered from one folder to the next, so several folders can be gathered
in a single pass.

Thumbnails are decoded a few at a time on the Tk event loop rather than all at
once: the grid appears immediately and fills in, instead of freezing for the
time it takes to read a hundred scans.
"""
__version__ = "2.3.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import tkinter as tk
from tkinter import ttk

import preview as preview_mod
import project as project_mod
import ui_dialogs

try:
    from i18n import _, ngettext
except ImportError:
    def _(s):
        return s

    def ngettext(singular, plural, n):
        return singular if n == 1 else plural

THUMB_W = 170
THUMB_H = 128
CELL_W = THUMB_W + 26
CELL_H = THUMB_H + 58
BATCH = 1          # thumbnails decoded per tick, so the wheel keeps answering

EMPTY_BG = "#dcdcdc"   # the waiting rectangle, before the thumbnail arrives
BORDER = "#9a9a9a"


class PhotoPicker(tk.Toplevel):
    """Browse folders and tick the photos to add. Chosen paths in `result`."""

    def __init__(self, parent, folder, already=(), recursive=False,
                 title=None):
        super().__init__(parent)
        self.result = []
        self._already = set(already)
        self._chosen = set()
        self._folder = folder or os.path.expanduser("~")
        self._paths = []
        self._vars = []
        self._cells = []
        self._images = []            # keeps Tk from discarding the thumbnails
        self._pending = []
        self._job = None
        self._reflow_job = None
        self._columns = 0

        self.title(title or _("Choose the photos to add"))
        self.transient(parent)
        self.geometry("1020x700")
        self.minsize(560, 440)

        self._preview = preview_mod.Preview(max_items=4096)
        self.var_recursive = tk.BooleanVar(value=recursive)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.update_idletasks()
        self.grab_set()
        self.load_folder(self._folder)
        self.wait_window(self)

    # ---------- construction ----------

    def _build(self):
        # The plain Tk frames below must wear the same colour as the ttk
        # widgets, otherwise a grey band shows under every photo and the
        # header looks as if it floated over the grid.
        style = ttk.Style(self)
        self._bg = (style.lookup("TFrame", "background")
                    or self.cget("background"))

        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(side="top", fill="x")
        bar.columnconfigure(1, weight=1)

        ttk.Label(bar, text=_("Folder:")).grid(row=0, column=0, sticky="w")
        self.lbl_folder = ttk.Label(bar, text="", anchor="w")
        self.lbl_folder.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(bar, text=_("Change…"),
                   command=self.change_folder).grid(row=0, column=2)
        ttk.Button(bar, text=_("Parent folder"),
                   command=self.go_up).grid(row=0, column=3, padx=(4, 0))

        options = ttk.Frame(self, padding=(10, 0, 10, 8))
        options.pack(side="top", fill="x")
        ttk.Checkbutton(options, text=_("Include subfolders"),
                        variable=self.var_recursive,
                        command=self._reload).pack(side="left")
        ttk.Button(options, text=_("Select all"),
                   command=lambda: self._set_all(True)).pack(side="left",
                                                             padx=(18, 0))
        ttk.Button(options, text=_("Select none"),
                   command=lambda: self._set_all(False)).pack(side="left",
                                                              padx=(6, 0))
        self.lbl_count = ttk.Label(options, text="")
        self.lbl_count.pack(side="right")

        ttk.Separator(self, orient="horizontal").pack(side="top", fill="x")

        bottom = ttk.Frame(self, padding=(10, 8))
        bottom.pack(side="bottom", fill="x")
        ttk.Button(bottom, text=_("Cancel"),
                   command=self._cancel).pack(side="right")
        self.btn_add = ttk.Button(bottom, text=_("Add"), command=self._accept)
        self.btn_add.pack(side="right", padx=(0, 8))
        self.lbl_hint = ttk.Label(bottom, text="", foreground="#777777")
        self.lbl_hint.pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        middle = ttk.Frame(self, padding=(10, 8))
        middle.pack(side="top", fill="both", expand=True)

        # A thin solid border marks where the grid begins and ends.
        box = tk.Frame(middle, borderwidth=1, relief="solid",
                       background=self._bg)
        box.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(box, highlightthickness=0,
                                background=self._bg)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical",
                               command=self.canvas.yview)
        scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)

        self.inner = ttk.Frame(self.canvas, padding=(8, 8))
        self.window = self.canvas.create_window((0, 0), window=self.inner,
                                                anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # The wheel is bound on the TOPLEVEL, not on the canvas: Tk delivers
        # the event to the widget under the pointer — a thumbnail, a tick box —
        # and does not pass it up to parent widgets. The toplevel, however, is
        # in the bind tags of every widget it contains, so it sees them all.
        self.bind("<MouseWheel>", self._on_wheel)      # Windows, macOS
        self.bind("<Button-4>", self._on_wheel)        # X11 wheel up
        self.bind("<Button-5>", self._on_wheel)        # X11 wheel down
        self.bind("<Prior>", lambda e: self._scroll_page(-1))
        self.bind("<Next>", lambda e: self._scroll_page(1))
        self.bind("<Home>", lambda e: self.canvas.yview_moveto(0))
        self.bind("<End>", lambda e: self.canvas.yview_moveto(1))

    # ---------- navigation ----------

    def change_folder(self):
        folder = ui_dialogs.pick_directory(self, title=_("Choose a folder"),
                                           initialdir=self._folder)
        if folder:
            self.load_folder(folder)

    def go_up(self):
        parent = os.path.dirname(self._folder.rstrip("/"))
        if parent and os.path.isdir(parent):
            self.load_folder(parent)

    def _reload(self):
        self.load_folder(self._folder)

    def load_folder(self, folder):
        """Show the images of a folder. Ticks made elsewhere are kept.

        Nothing is ticked on arrival. A folder crossed on the way to another
        one used to come away with every photograph in it ticked, and since
        ticks follow from folder to folder, a wrong turn was both easy to
        make and invisible afterwards. "Select all" is one click for the
        folders that really are wanted whole."""
        self._stop_thumbnails()
        self._folder = folder
        self.lbl_folder.configure(text=folder)
        self._paths = [p for p in
                       project_mod.scan_folder(folder,
                                               self.var_recursive.get())]
        self._build_grid()
        self._refresh_count()
        self._start_thumbnails()

    # ---------- the grid ----------

    def _build_grid(self):
        for cell, _holder in self._cells:
            cell.destroy()
        self._cells = []
        self._vars = []
        self._images = []
        self._columns = 0

        if not self._paths:
            empty = ttk.Frame(self.inner, padding=(10, 20))
            label = ttk.Label(empty, text=_("No image in this folder."))
            label.pack()
            empty.grid(row=0, column=0, sticky="w")
            self._cells.append((empty, label))
            self._on_inner_configure()
            return

        for index, path in enumerate(self._paths):
            known = path in self._already
            var = tk.BooleanVar(value=(path in self._chosen) and not known)
            var.trace_add("write",
                          lambda *a, i=index: self._on_tick(i))
            self._vars.append(var)

            # Every cell has the same fixed size, and the thumbnail is centred
            # inside a box of fixed size: otherwise a portrait photograph makes
            # its cell taller than its neighbours and the tick boxes of a row
            # no longer line up.
            cell = tk.Frame(self.inner, width=CELL_W, height=CELL_H,
                            background=self._bg)
            cell.pack_propagate(False)

            box = tk.Frame(cell, width=THUMB_W, height=THUMB_H,
                           background=self._bg)
            box.pack_propagate(False)
            box.pack(side="top", pady=(4, 0))

            holder = tk.Label(box, background=EMPTY_BG, text="…",
                              foreground="#888888")
            holder.place(relx=0.5, rely=0.5, anchor="center",
                         relwidth=1.0, relheight=1.0)

            text = self._short(os.path.basename(path))
            check = ttk.Checkbutton(cell, variable=var, text=text)
            check.pack(side="top", anchor="w", padx=(3, 0), pady=(4, 0))

            status = ttk.Label(cell,
                               text=_("already in the slideshow") if known
                               else "", foreground="#777777")
            status.pack(side="top", anchor="w", padx=(3, 0))

            if known:
                check.state(["disabled"])
            else:
                holder.bind("<Button-1>",
                            lambda e, i=index: self._toggle(i))
            self._cells.append((cell, holder))
        self._reflow(force=True)

    @staticmethod
    def _short(name, width=22):
        if len(name) <= width:
            return name
        return name[: width - 9] + "…" + name[-8:]

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        if self._reflow_job is not None:
            self.after_cancel(self._reflow_job)
        self._reflow_job = self.after(120, self._reflow)

    def _on_inner_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif getattr(event, "delta", 0):
            delta = -1 if event.delta > 0 else 1
        else:
            return
        self.canvas.yview_scroll(delta * 3, "units")
        return "break"

    def _scroll_page(self, direction):
        self.canvas.yview_scroll(direction, "pages")
        return "break"

    def _reflow(self, force=False):
        self._reflow_job = None
        if not self._paths:
            return
        width = max(self.canvas.winfo_width(), CELL_W)
        columns = max(1, (width - 20) // CELL_W)
        if columns == self._columns and not force:
            return
        self._columns = columns
        for index, (cell, _holder) in enumerate(self._cells):
            cell.grid(row=index // columns, column=index % columns,
                      sticky="nw")
        self.canvas.yview_moveto(0)
        self._on_inner_configure()

    # ---------- thumbnails ----------

    def _start_thumbnails(self):
        self._pending = list(range(len(self._paths)))
        self._stop_thumbnails()
        self._job = self.after(10, self._load_batch)

    def _stop_thumbnails(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _load_batch(self):
        self._job = None
        done = 0
        while self._pending and done < BATCH:
            index = self._pending.pop(0)
            if index >= len(self._cells):
                continue
            path = self._paths[index]
            image, info = self._preview.get(path, THUMB_W, THUMB_H)
            cell, holder = self._cells[index]
            if image is None:
                holder.configure(text=_("unreadable"), foreground="#b00020")
            else:
                self._images.append(image)
                holder.configure(image=image, text="", background=self._bg)
            done += 1
        if self._pending:
            self._job = self.after(1, self._load_batch)

    # ---------- ticks ----------

    def _on_tick(self, index):
        if index >= len(self._paths) or index >= len(self._vars):
            return
        path = self._paths[index]
        if self._vars[index].get():
            self._chosen.add(path)
        else:
            self._chosen.discard(path)
        self._refresh_count()

    def _toggle(self, index):
        if index < len(self._vars):
            self._vars[index].set(not self._vars[index].get())

    def _set_all(self, value):
        for index, var in enumerate(self._vars):
            if self._paths[index] in self._already:
                continue
            var.set(value)

    def _refresh_count(self):
        here = sum(1 for p in self._paths
                   if p in self._chosen and p not in self._already)
        total = len(self._chosen)
        self.lbl_count.configure(
            text=_("{here} of {shown} in this folder").format(
                here=here, shown=len(self._paths)))
        self.btn_add.configure(
            text=ngettext("Add {n} photo", "Add {n} photos",
                          total).format(n=total) if total else _("Add"))
        if total > here:
            elsewhere = total - here
            self.lbl_hint.configure(
                text=ngettext(
                    "{n} photo ticked in another folder is kept.",
                    "{n} photos ticked in other folders are kept.",
                    elsewhere).format(n=elsewhere))
        else:
            self.lbl_hint.configure(text="")

    # ---------- leaving ----------

    def _accept(self):
        self._stop_thumbnails()
        self._pending = []
        self.result = sorted(self._chosen)
        self.destroy()

    def _cancel(self):
        self._stop_thumbnails()
        self._pending = []
        self.result = []
        self.destroy()


def choose(parent, folder, already=(), recursive=False, title=None):
    """Open the picker on a folder and return the chosen paths."""
    return PhotoPicker(parent, folder, already=already, recursive=recursive,
                       title=title).result
