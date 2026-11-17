#!/usr/bin/env python3
"""
ui_rejects.py — The photographs taken out of this slideshow.

Taking a photograph out of the slideshow records that it is not wanted in
it, so that importing by tag again does not bring it back. That record has
to be visible and undoable, otherwise a photograph removed by accident is
gone for good from every later import with nothing to show why.

Nothing here touches the files. A rejection belongs to the slideshow: it
lives in the project file beside the list of photographs, and forgetting it
only means the photograph may be imported again.
"""
__version__ = "1.0.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import tkinter as tk
from tkinter import ttk

import ui_dialogs

try:
    from i18n import _, ngettext
except ImportError:
    def _(s):
        return s

    def ngettext(singular, plural, n):
        return singular if n == 1 else plural


class RejectedList(tk.Toplevel):
    """Show the rejected photographs and let the rejection be forgotten."""

    def __init__(self, parent, project, title=None):
        super().__init__(parent)
        self.withdraw()
        self.project = project
        self.changed = False

        self.title(title or _("Rejected photographs"))
        self.geometry("760x460")
        self.minsize(560, 340)
        self.transient(parent)

        self._paths = []
        self._build()
        self._refill()

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())
        self.update_idletasks()
        self._centre(parent)
        self.deiconify()
        self.grab_set()
        self.wait_window(self)

    def _build(self):
        head = ttk.Frame(self, padding=(10, 8))
        head.pack(fill="x")
        ttk.Label(head, justify="left", wraplength=700, text=_(
            "These photographs were taken out of the slideshow, so importing "
            "by tag will not bring them back. The files themselves are "
            "untouched, and their tags in digiKam are unchanged.")
        ).pack(anchor="w")

        middle = ttk.Frame(self, padding=(10, 4))
        middle.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(middle, columns=("name", "folder"),
                                 show="headings", selectmode="extended")
        self.tree.heading("name", text=_("File"))
        self.tree.heading("folder", text=_("Folder"))
        self.tree.column("name", width=230, anchor="w", stretch=False)
        self.tree.column("folder", width=480, anchor="w")
        scroll = ttk.Scrollbar(middle, orient="vertical",
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        foot = ttk.Frame(self, padding=(10, 8))
        foot.pack(fill="x")
        self.lbl_count = ttk.Label(foot, text="")
        self.lbl_count.pack(side="left")
        ttk.Button(foot, text=_("Close"),
                   command=self._close).pack(side="right")
        self.btn_all = ttk.Button(foot, text=_("Forget them all"),
                                  command=self._forget_all)
        self.btn_all.pack(side="right", padx=(0, 8))
        self.btn_forget = ttk.Button(foot, text=_("Forget the rejection"),
                                     command=self._forget_selected)
        self.btn_forget.pack(side="right", padx=(0, 8))

    def _centre(self, parent):
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px = py = pw = ph = 0
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("+{}+{}".format(px + max(0, (pw - w) // 2),
                                      py + max(0, (ph - h) // 3)))

    def _refill(self):
        self.tree.delete(*self.tree.get_children())
        self._paths = self.project.rejected_photos()
        for index, path in enumerate(self._paths):
            self.tree.insert("", "end", iid=str(index),
                             values=(os.path.basename(path),
                                     os.path.dirname(path)))
        count = len(self._paths)
        self.lbl_count.configure(
            text=ngettext("{n} rejected photograph",
                          "{n} rejected photographs", count).format(n=count)
            if count else _("No photograph has been rejected."))
        state = "!disabled" if count else "disabled"
        self.btn_all.state([state])
        self.btn_forget.state([state])

    def _selected_paths(self):
        return [self._paths[int(iid)] for iid in self.tree.selection()
                if 0 <= int(iid) < len(self._paths)]

    def _forget_selected(self):
        chosen = self._selected_paths()
        if not chosen:
            ui_dialogs.info(self, _("Choose the photographs whose rejection "
                                    "should be forgotten."))
            return
        if self.project.unreject(chosen):
            self.changed = True
        self._refill()

    def _forget_all(self):
        count = len(self._paths)
        if not count:
            return
        if not ui_dialogs.confirm(
                self,
                ngettext(
                    "Forget the rejection of {n} photograph? It may then be "
                    "imported by tag again.",
                    "Forget the rejection of {n} photographs? They may then "
                    "be imported by tag again.", count).format(n=count),
                ok_text=_("Forget")):
            return
        if self.project.clear_rejections():
            self.changed = True
        self._refill()

    def _close(self):
        self.destroy()


def show(parent, project, title=None):
    """Open the window. Returns True when a rejection was forgotten."""
    return RejectedList(parent, project, title=title).changed
